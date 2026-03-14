# M12c: Setup Lobby — Design Spec

> GUI-based simulation setup. The viewer's initial state is a configuration lobby where the user sets parameters and launches the simulation — replacing CLI flags with a visual form. One component, one new WebSocket message type, one backend refactor.

## Scope

**In scope:**
- Setup lobby screen integrated into the existing React viewer
- Sidebar + preview layout (left: controls, right: scenario preview)
- Six configuration controls: scenario, seed, turns, civs, regions, model selectors
- Resume/fork from saved state.json via file picker
- WebSocket-only protocol — `start` command, `lobby` server state
- Backend decoupling: WebSocket server starts in lobby state, simulation starts on `start` command

**Out of scope:**
- Scenario editor (create/modify YAML) — deferred, schema changes across M13-M18
- Multi-client lobby
- History of past runs
- Settings persistence across sessions
- Batch mode GUI (fundamentally different workflow — stays CLI)
- Output path configuration (sensible defaults)

---

## Architecture

### Integration Point

The setup lobby is the viewer's initial state in live mode. The flow:

1. User runs `chronicler --live` — WebSocket server starts in **lobby** state
2. User opens viewer — WebSocket connects, receives lobby init, renders setup panel
3. User configures parameters, clicks Launch
4. Client sends `start` command over WebSocket
5. Server validates, generates world, transitions to **running** state
6. Server sends running init (with `world_state`, `history`, etc.) — viewer transitions to the existing chronicle view
7. If validation fails, server sends `error` — viewer stays in lobby with error displayed

No HTTP endpoints. No second server. No new ports. The WebSocket connection established for the lobby is the same connection used for live streaming.

### Layout Continuity

The setup lobby uses the **sidebar + preview** layout (Option B):

- **Left sidebar** — configuration controls, same position as the intervention panel during running state
- **Right panel** — scenario preview (region map, civ list, description)

The mental model: left side = controls, right side = world. Before launch, "controls" means configuration; after launch, "controls" means interventions. The transition is a content swap, not a layout change.

---

## Protocol Changes

### Server States

The server now has an explicit lifecycle: `lobby → running → completed`.

- **lobby** — WebSocket server is up, no simulation running. Accepts `start` commands. Rejects `continue`, `inject`, `set`, `fork`.
- **running** — simulation active. Existing M12 protocol applies unchanged.
- **completed** — simulation finished. Existing behavior.

`_server_state` is only mutated in the WebSocket handler thread. The main thread communicates state changes via the existing queue mechanism.

### Lobby Init Message (server → client)

Sent on client connect when server is in lobby state:

```json
{
  "type": "init",
  "state": "lobby",
  "scenarios": [
    {
      "file": "rise_and_fall.yaml",
      "name": "Rise and Fall",
      "description": "Two empires competing for dominance...",
      "world_name": "Aetheris",
      "civs": [
        {"name": "Kethani Empire", "values": ["Trade", "Order"]}
      ],
      "regions": [
        {"name": "Ashenmoor", "terrain": "plains", "x": 0.3, "y": 0.7}
      ]
    }
  ],
  "models": ["LFM2-24B", "claude-sonnet-4-20250514"],
  "defaults": {
    "turns": 50,
    "civs": 4,
    "regions": 8,
    "seed": null,
    "pause_every": 10
  }
}
```

Scenario data is parsed directly from YAML files — no world generation at startup. Only scenarios that don't define explicit civs/regions fall back to empty arrays. The full scenario list is sent upfront so preview updates are instant with zero round trips.

### Running Init Message (server → client)

The existing init message gains a `state` field:

```json
{
  "type": "init",
  "state": "running",
  "total_turns": 50,
  "world_state": { ... },
  "history": [],
  ...
}
```

For backward compatibility, `init` messages without a `state` field are treated as `"running"` by the client. Comment in code: "Pre-lobby servers don't send state field; treat absence as running."

### Start Command (client → server)

```json
{
  "type": "start",
  "scenario": "rise_and_fall.yaml",
  "turns": 50,
  "seed": 42,
  "civs": 4,
  "regions": 8,
  "sim_model": "LFM2-24B",
  "narrative_model": "LFM2-24B",
  "resume_state": null
}
```

- `seed: null` means server-generated. The server creates a seed and echoes it back in the running init's `metadata.seed`.
- `resume_state` is either `null` (fresh run) or a parsed `WorldState` JSON object (not a file path — no filesystem coupling). When present, `scenario`, `civs`, and `regions` are ignored.
- `scenario: null` means procedural generation (no scenario YAML).

**Server handling:**

1. If `_server_state != "lobby"`, respond with `error: "Simulation already running"`
2. Validate required fields
3. Store params in `_start_params`
4. Set `_server_state = "running"` (handler thread only)
5. Set `start_event` — unblocks main thread

**All existing message types unchanged:** `turn`, `paused`, `ack`, `forked`, `completed`, `error`, `speed`, `continue`, `inject`, `set`, `fork`, `quit`.

---

## Backend Changes

### `LiveServer.__init__` — New Fields

```python
self.start_event = threading.Event()       # signals "user clicked Launch"
self._start_params: dict | None = None     # validated start command payload
self._server_state: str = "lobby"          # "lobby" | "running" | "completed"
self._lobby_init: dict | None = None       # cached lobby init message
```

### Handler Changes

The `start` command is handled in the WebSocket message handler:

```python
if msg_type == "start":
    if self._server_state != "lobby":
        await websocket.send(json.dumps({
            "type": "error",
            "message": "Simulation already running",
        }))
        continue
    self._start_params = msg
    self._server_state = "running"
    self.start_event.set()
    continue
```

On client connect, the handler sends whichever init matches the current state:

- Lobby: sends `_lobby_init`
- Running: sends `_init_data` (existing behavior)

### `run_live()` Refactor

The function splits into two phases:

**Phase 1 — Lobby:**

```python
server = LiveServer(port=port)
server._lobby_init = build_lobby_init(args)
server.start()
print(f"Lobby ready on ws://localhost:{actual_port}")

# Block until client sends start (interruptible)
while not server.start_event.wait(timeout=1.0):
    pass  # allows Ctrl+C to interrupt

params = server._start_params
```

**Phase 2 — Simulation (same as current, but reads params from client):**

```python
if params.get("resume_state"):
    world = WorldState.model_validate(params["resume_state"])
else:
    seed = params.get("seed")  # None = server generates
    world = generate_world(
        seed=seed,
        num_regions=params.get("regions", 8),
        num_civs=params.get("civs", 4),
    )
    if params.get("scenario"):
        scenario_config = load_scenario(params["scenario"])
        apply_scenario(world, scenario_config)

# ... execute_run() with on_turn_cb, quit_check — unchanged
```

### `build_lobby_init()` — New Helper

Scans `scenarios/*.yaml`, parses each with `yaml.safe_load`, extracts preview data directly from the YAML (no world generation). Returns the lobby init payload.

```python
def build_lobby_init(args) -> dict:
    scenarios = []
    scenario_dir = Path("scenarios")
    if scenario_dir.exists():
        for f in sorted(scenario_dir.glob("*.yaml")):
            with open(f) as fh:
                data = yaml.safe_load(fh)
            scenarios.append({
                "file": f.name,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "world_name": data.get("world_name", f.stem),
                "civs": [
                    {"name": c["name"], "values": c.get("values", [])}
                    for c in data.get("civilizations", [])
                ],
                "regions": [
                    {"name": r["name"], "terrain": r.get("terrain", ""),
                     "x": r.get("x"), "y": r.get("y")}
                    for r in data.get("regions", [])
                ],
            })
    return {
        "type": "init",
        "state": "lobby",
        "scenarios": scenarios,
        "models": _get_available_models(args),
        "defaults": {
            "turns": 50, "civs": 4, "regions": 8,
            "seed": None, "pause_every": 10,
        },
    }
```

---

## Frontend Changes

### New Types (`types.ts`)

```typescript
export interface ScenarioInfo {
  file: string;
  name: string;
  description: string;
  world_name: string;
  civs: { name: string; values: string[] }[];
  regions: { name: string; terrain: string; x: number | null; y: number | null }[];
}

export interface LobbyInit {
  scenarios: ScenarioInfo[];
  models: string[];
  defaults: {
    turns: number;
    civs: number;
    regions: number;
    seed: number | null;
    pause_every: number;
  };
}

export interface StartCommand {
  type: "start";
  scenario: string | null;
  turns: number;
  seed: number | null;
  civs: number;
  regions: number;
  sim_model: string;
  narrative_model: string;
  resume_state: WorldState | null;
}
```

`Command` union extended to include `StartCommand`.

### Hook Changes (`useLiveConnection.ts`)

New state fields:

```typescript
serverState: "connecting" | "lobby" | "starting" | "running" | "completed";
lobbyInit: LobbyInit | null;
sendStart: (params: Omit<StartCommand, "type">) => void;
```

The `init` message handler branches on `msg.state`:

- `"lobby"` → sets `serverState` to `"lobby"`, populates `lobbyInit`
- `"running"` (or absent) → sets `serverState` to `"running"`, populates `bundle` (existing behavior)

`sendStart` sets `serverState` to `"starting"` before sending, preventing double-submission. On `error` received while in `"starting"` state, reverts to `"lobby"`.

### App State Machine (`App.tsx`)

Live mode gates on `serverState`:

| State | Renders |
|-------|---------|
| `connecting` | Centered "Connecting to simulation..." message |
| `lobby` | `SetupLobby` component (sidebar + preview) |
| `starting` | `SetupLobby` with disabled Launch button + spinner |
| `running` | Existing `Layout` component (chronicle viewer) |
| `completed` | Existing `Layout` component |

Static mode (no `?ws=` param) is unchanged — file drop zone / picker.

### New Component: `SetupLobby`

**Props:**

```typescript
interface SetupLobbyProps {
  lobbyInit: LobbyInit;
  onLaunch: (params: Omit<StartCommand, "type">) => void;
  starting: boolean;
  error: string | null;
}
```

**Layout:** Sidebar (left, ~300px) + Preview Panel (right, flex-1). Full viewport height, same dark theme as the viewer.

**Sidebar controls (top to bottom):**

1. **Scenario** — `<select>` dropdown. First option: `"(Procedural)"` for no scenario. Populated from `lobbyInit.scenarios`. Changing selection updates the preview panel instantly (data already loaded).

2. **Seed** — number input + dice button (randomize). Placeholder: `"Random"`. Empty value = `null` = server picks.

3. **Turns** — number input. Pre-filled from `lobbyInit.defaults.turns`.

4. **Civs / Regions** — two number inputs, side by side. Pre-filled from defaults. **Civs disables independently** when `selectedScenario.civs.length > 0`. **Regions disables independently** when `selectedScenario.regions.length > 0`. Shows scenario values when disabled.

5. **Sim Model / Narrative Model** — two `<select>` dropdowns from `lobbyInit.models`. Plus a `"Custom..."` option that reveals a text input for arbitrary endpoint URLs.

6. **Resume / Fork** — file input styled as a drop zone. Accepts `.json`. On file load:
   - Parses JSON, validates structurally (has `turn` as number, `civilizations` as array)
   - If invalid: inline error under drop zone ("Invalid save file — missing required fields")
   - If valid: disables scenario/civs/regions, shows badge "Resuming from Turn N", preview shows loaded world state
   - `✕` button clears resume state and re-enables fields

**Launch button** — full-width green button at bottom of sidebar. Text: `"▶ LAUNCH SIMULATION"`. During `starting`: disabled, shows spinner + `"Starting..."`.

**Error banner** — red banner above Launch button when `error` is non-null. Shows server error message. Clears on next user interaction.

**Validation** — frontend-only, trivial type constraints:
- Turns > 0
- Seed ≥ 0 (or empty)
- Civs > 0, Regions > 0

All real validation server-side. No duplicated business logic.

### Preview Panel

Shows details for the selected scenario. Three sections:

1. **Header** — scenario name, world name, description
2. **Region map** — extracted `RegionMap` component (subset of `TerritoryMap`) taking `regions: {name, terrain, x, y}[]`. Terrain coloring only, no faction/controller layer.
3. **Civ list** — read-only cards showing name and values

**Empty state** (Procedural selected or no scenario): centered placeholder with map icon and "Select a scenario to preview."

**Resume state** (state.json loaded): preview shows loaded world state — region map colored by controllers, civ list with current stats. Visual confirmation of correct save file.

---

## Validation Strategy

**Frontend validation:** Trivial type constraints only (positive integers, non-negative seed). Prevents obviously broken payloads.

**Backend validation:** Server is source of truth. Validates scenario file exists, parameter ranges, resume_state structure. Returns `error` message on failure — client displays it and stays in lobby.

**No duplicated validation logic** between frontend and backend.

---

## Testing

### Backend (`test_live.py` additions)

- **Lobby init correctness** — `build_lobby_init` scans scenario dir, returns correct shape with preview data parsed from YAML
- **Start command validation** — rejects `start` when already running, rejects missing fields, accepts valid params and sets `start_event`
- **State transitions** — lobby → running on valid start; lobby init on reconnect during lobby; running init on reconnect during running
- **Resume path** — `start` with `resume_state` containing valid WorldState skips world gen
- **Lobby reconnection** — client disconnect + reconnect during lobby receives lobby init again
- **Seed round-trip** — client sends `seed: null`, server generates seed, running init echoes valid integer seed in `metadata.seed`

### Frontend (`useLiveConnection.test.ts` additions)

- **Lobby init handling** — receives `init` with `state: "lobby"`, sets `serverState` to `"lobby"`, populates `lobbyInit`
- **`sendStart` transitions** — sets `serverState` to `"starting"`, sends `start` on WebSocket
- **Error recovery** — server sends `error` after start, `serverState` reverts to `"lobby"`
- **Backward compat** — `init` without `state` field treated as `"running"`
- **Full retry sequence** — starting → error → lobby → retry → starting → running. Verifies second `sendStart` works correctly after error recovery

### Frontend (`SetupLobby.test.tsx`)

- **Renders all six controls** with values from `lobbyInit.defaults`
- **Scenario selection** — disables civs field when scenario has civs, disables regions field independently when scenario has regions
- **Resume file** — valid file shows badge + disables fields, invalid file shows inline error, clear button re-enables
- **Launch button** — disabled during `starting`, calls `onLaunch` with correct param shape

### Not Testing

- E2E browser tests (out of scope)
- Scenario YAML content
- Existing turn/pause/ack handling (already covered)

---

## File Changes Summary

| File | Change |
|------|--------|
| `src/chronicler/live.py` | Add `start_event`, `_start_params`, `_server_state`, `_lobby_init` to `LiveServer`. Add `start` handler. Refactor `run_live()` to block on `start_event`. Add `build_lobby_init()`. |
| `viewer/src/types.ts` | Add `ScenarioInfo`, `LobbyInit`, `StartCommand`. Extend `Command` union. |
| `viewer/src/hooks/useLiveConnection.ts` | Add `serverState`, `lobbyInit`, `sendStart`. Branch `init` handler on `msg.state`. |
| `viewer/src/App.tsx` | Gate live mode on `serverState` switch. Render `SetupLobby` for lobby/starting. |
| `viewer/src/components/SetupLobby.tsx` | **New file.** Sidebar + preview layout, six controls, launch button. |
| `viewer/src/components/RegionMap.tsx` | **New file.** Extracted from `TerritoryMap` — terrain-only region positioning. |
| `tests/test_live.py` | Add lobby init, start validation, state transition, seed round-trip tests. |
| `viewer/src/hooks/useLiveConnection.test.ts` | Add lobby, sendStart, error recovery, backward compat, retry sequence tests. |
| `viewer/src/components/SetupLobby.test.tsx` | **New file.** Control rendering, disable logic, resume, launch tests. |
