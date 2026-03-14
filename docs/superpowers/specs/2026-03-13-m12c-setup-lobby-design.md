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

- **lobby** — WebSocket server is up, no simulation running. Accepts `start` commands. Rejects `continue`, `inject`, `set`, `fork`. If the client disconnects and reconnects during lobby, the server sends the lobby init again — the handler's existing connect logic handles this naturally.
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
      "file": "dead_miles.yaml",
      "name": "The Dead Miles",
      "description": "Post-apocalyptic wasteland survival...",
      "world_name": "The Dead Miles",
      "civs": [
        {"name": "The Convoy", "values": ["Survival", "Freedom"]}
      ],
      "regions": [
        {"name": "Salt Flats", "terrain": "desert", "x": null, "y": null}
      ]
    }
  ],
  "models": ["LFM2-24B", "claude-sonnet-4-20250514"],
  "defaults": {
    "turns": 50,
    "civs": 4,
    "regions": 8,
    "seed": null
  }
}
```

Scenario data is parsed directly from YAML files — no world generation at startup. Only scenarios that don't define explicit civs/regions fall back to empty arrays. The full scenario list is sent upfront so preview updates are instant with zero round trips.

**Note:** `pause_every` is not included in `defaults` — it uses the CLI default (or `--reflection-interval`) and is not configurable from the lobby. The lobby controls parameters that affect *what* is simulated, not *how often* it pauses. Example uses illustrative data; field availability depends on scenario YAML content (`values` defaults to `[]` if absent).

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
  "scenario": "dead_miles.yaml",
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

The `start` command joins `speed` and `quit` as an **always-accepted** command — it must be dispatched **before** the existing `if not self._paused` gate that rejects commands outside pause intervals. The dispatch order in the handler is:

1. `speed` — always accepted (existing)
2. `quit` — always accepted (existing)
3. `start` — always accepted, lobby-only (new)
4. `if not self._paused: reject` — existing gate for all other commands
5. `continue`, `inject`, `set`, `fork` — paused-only (existing)

```python
# After speed and quit handling, before the paused gate:
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

# Existing paused gate follows:
if not self._paused:
    await websocket.send(json.dumps({...}))
    continue
```

On client connect, the handler sends whichever init matches the current state:

- Lobby: sends `_lobby_init`
- Running: sends `_init_data` (existing behavior)

**Reconnect during world generation:** There is a brief window after `_server_state = "running"` but before `_init_data` is populated (world generation hasn't completed yet). If a client reconnects during this window, the handler sends a minimal acknowledgment `{"type": "init", "state": "starting"}` so the client can show "World generating..." instead of appearing stuck. The client already handles `"starting"` as a local state — receiving it from the server during this window reuses the same UI (disabled Launch button + spinner). Once world generation completes and the first turn fires, the full running init is sent as usual.

**Threading note:** `_start_params` is written by the handler thread and read by the main thread after `start_event.wait()`. The `threading.Event` provides a happens-before guarantee (set before `event.set()`, read after `event.wait()`). Safe under CPython GIL; no additional lock needed.

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
    # Resolve seed: None means server-generated random
    seed = params.get("seed")
    if seed is None:
        seed = random.randint(0, 2**31 - 1)

    world = generate_world(
        seed=seed,
        num_regions=params.get("regions", 8),
        num_civs=params.get("civs", 4),
    )
    if params.get("scenario"):
        scenario_config = load_scenario(Path("scenarios") / params["scenario"])
        apply_scenario(world, scenario_config)

# Construct LLM clients from client-selected models.
# Currently main.py constructs clients before calling run_live().
# With the lobby, client construction moves here — after the start
# command provides the model names.
sim_model = params.get("sim_model")
narrative_model = params.get("narrative_model")
sim_client = make_llm_client(sim_model, args) if sim_model else None
narrative_client = make_llm_client(narrative_model, args) if narrative_model else None

# ... execute_run() with on_turn_cb, quit_check — unchanged
```

**LLM client construction:** The existing `main.py` builds `sim_client` and `narrative_client` from CLI args before dispatching to `run_live()`. With the lobby, this construction moves into `run_live()` Phase 2 — the model names come from the `start` command, not CLI args. The existing `create_clients(local_url, sim_model, narrative_model)` in `llm.py` already handles role-specific temperature differentiation (`temperature=0.3` for sim, `temperature=0.8` for narrative). Phase 2 calls `create_clients(local_url=args.local_url, sim_model=sim_model, narrative_model=narrative_model)` directly — no new helper needed. The `run_live()` signature drops `sim_client` and `narrative_client` parameters; `main.py` no longer constructs them upfront for live mode.

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
            "seed": None,
        },
    }
```

**`_get_available_models(args)`:** Returns a list of model name strings available for the sim and narrative dropdowns. Implementation: returns a hardcoded list of known models (e.g., `["LFM2-24B"]`) plus any model names specified via CLI args (`--sim-model`, `--narrative-model`). Optionally queries LM Studio at `args.local_url/v1/models` to discover loaded models — wrapped in `try/except` with a 500ms timeout, falling back to the hardcoded list if LM Studio is down or slow. The "Custom..." option in the frontend dropdown handles arbitrary endpoints not in this list.

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

`StartCommand` is a **separate type**, not added to the `Command` union. The `Command` union remains the type for intervention commands sent via `sendCommand`. `StartCommand` is only sent via the dedicated `sendStart` method, preventing accidental misuse through the generic `sendCommand` path.

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
2. **Region map** — extracted `RegionMap` component (subset of `TerritoryMap`) taking `regions: {name, terrain, x, y}[]`. Terrain coloring only, no faction/controller layer. **When x/y are null** (most existing scenarios don't define coordinates), `RegionMap` positions nodes using a simple circle layout by index — deterministic, trivial to implement, good enough for preview. (Future enhancement: d3-force with fixed iteration count for more organic layouts.) This matches how `TerritoryMap` already uses `circleLayout` as a fallback for null coordinates.
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
| `src/chronicler/live.py` | Add `start_event`, `_start_params`, `_server_state`, `_lobby_init` to `LiveServer`. Add `start` handler (before paused gate). Refactor `run_live()` to block on `start_event`. Add `build_lobby_init()`, `_get_available_models()`. Move LLM client construction into `run_live()` Phase 2. |
| `src/chronicler/main.py` | Extract `make_llm_client()` helper from existing client construction. Skip client construction for `--live` mode (deferred to `run_live()`). |
| `viewer/src/types.ts` | Add `ScenarioInfo`, `LobbyInit`, `StartCommand` (separate from `Command` union). |
| `viewer/src/hooks/useLiveConnection.ts` | Add `serverState`, `lobbyInit`, `sendStart`. Branch `init` handler on `msg.state`. |
| `viewer/src/App.tsx` | Gate live mode on `serverState` switch. Render `SetupLobby` for lobby/starting. |
| `viewer/src/components/SetupLobby.tsx` | **New file.** Sidebar + preview layout, six controls, launch button. |
| `viewer/src/components/RegionMap.tsx` | **New file.** Extracted from `TerritoryMap` — terrain-only region positioning with null-coordinate layout. |
| `viewer/src/components/RegionMap.test.tsx` | **New file.** Null coordinate handling, terrain coloring, deterministic layout. |
| `tests/test_live.py` | Add lobby init, start validation, state transition, seed round-trip tests. |
| `viewer/src/hooks/useLiveConnection.test.ts` | Add lobby, sendStart, error recovery, backward compat, retry sequence tests. |
| `viewer/src/components/SetupLobby.test.tsx` | **New file.** Control rendering, disable logic, resume, launch tests. |
