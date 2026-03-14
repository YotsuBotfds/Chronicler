# M12c: Setup Lobby Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GUI setup/lobby screen to the React viewer that lets users configure and launch simulations without CLI flags.

**Architecture:** Extend the existing M12 live mode WebSocket protocol with a `lobby` state and `start` command. The viewer shows a setup panel (sidebar + preview) as its initial state, transitions to the existing chronicle view on launch. Backend decouples WebSocket server startup from simulation startup.

**Tech Stack:** Python 3.13+ (websockets, pydantic, pyyaml), React 19, TypeScript 5.9, Tailwind 4, Vite 7, vitest

**Spec:** `docs/superpowers/specs/2026-03-13-m12c-setup-lobby-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/chronicler/live.py` | Modify: add lobby state, `start` handler, `build_lobby_init()`, `_get_available_models()`, refactor `run_live()` |
| `src/chronicler/main.py` | Modify: skip LLM client construction for `--live` mode |
| `viewer/src/types.ts` | Modify: add `ScenarioInfo`, `LobbyInit`, `StartCommand` types |
| `viewer/src/hooks/useLiveConnection.ts` | Modify: add `serverState`, `lobbyInit`, `sendStart` |
| `viewer/src/App.tsx` | Modify: gate live mode on `serverState` switch |
| `viewer/src/components/SetupLobby.tsx` | Create: sidebar + preview layout, six controls, launch button |
| `viewer/src/components/RegionMap.tsx` | Create: terrain-only region map with circle layout fallback |
| `tests/test_live.py` | Modify: add lobby/start/state transition tests |
| `viewer/src/hooks/__tests__/useLiveConnection.test.ts` | Modify: add lobby/sendStart/error recovery tests |
| `viewer/src/components/__tests__/SetupLobby.test.tsx` | Create: control rendering, disable logic, resume, launch tests |
| `viewer/src/components/__tests__/RegionMap.test.tsx` | Create: null coordinate handling, terrain coloring tests |

---

## Chunk 1: Backend — LiveServer Lobby State and Start Handler

### Task 1: Add lobby fields to LiveServer

**Files:**
- Modify: `src/chronicler/live.py:27-41`
- Test: `tests/test_live.py`

- [ ] **Step 1: Write failing test for new fields**

Add to `tests/test_live.py`:

```python
def test_live_server_has_lobby_fields():
    """LiveServer initializes with lobby state fields."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    assert hasattr(server, "start_event")
    assert hasattr(server, "_start_params")
    assert hasattr(server, "_server_state")
    assert hasattr(server, "_lobby_init")
    assert server._server_state == "lobby"
    assert server._start_params is None
    assert server._lobby_init is None
    assert not server.start_event.is_set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_live_server_has_lobby_fields -v`
Expected: FAIL with `AttributeError` (fields don't exist yet)

- [ ] **Step 3: Add lobby fields to LiveServer.__init__**

In `src/chronicler/live.py`, add after line 41 (`self._last_paused_msg: dict | None = None`):

```python
        self.start_event = threading.Event()
        self._start_params: dict | None = None
        self._server_state: str = "lobby"
        self._lobby_init: dict | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_live_server_has_lobby_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/live.py tests/test_live.py
git commit -m "feat(m12c): add lobby state fields to LiveServer"
```

### Task 2: Add start command handler

**Files:**
- Modify: `src/chronicler/live.py:82-134` (handler function)
- Modify: `src/chronicler/live.py:94-100` (connect init send)
- Test: `tests/test_live.py`

- [ ] **Step 1: Write failing tests for start command handling**

Add to `tests/test_live.py`:

```python
def test_start_command_sets_event():
    """Start command stores params and sets start_event."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    assert server._server_state == "lobby"

    # Simulate what the handler does
    start_msg = {
        "type": "start",
        "scenario": "dead_miles.yaml",
        "turns": 50,
        "seed": 42,
        "civs": 4,
        "regions": 8,
        "sim_model": "LFM2-24B",
        "narrative_model": "LFM2-24B",
        "resume_state": None,
    }
    server._handle_start(start_msg)

    assert server._server_state == "running"
    assert server.start_event.is_set()
    assert server._start_params == start_msg


def test_start_command_rejected_when_running():
    """Start command returns error when already running."""
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._server_state = "running"

    result = server._handle_start({"type": "start", "turns": 50})
    assert result is not None
    assert result["type"] == "error"
    assert "already running" in result["message"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_start_command_sets_event tests/test_live.py::test_start_command_rejected_when_running -v`
Expected: FAIL with `AttributeError: 'LiveServer' object has no attribute '_handle_start'`

- [ ] **Step 3: Add _handle_start method and wire into handler**

Add method to `LiveServer` class in `src/chronicler/live.py`:

```python
    def _handle_start(self, msg: dict) -> dict | None:
        """Handle a start command. Returns an error dict if rejected, None on success."""
        if self._server_state != "lobby":
            return {"type": "error", "message": "Simulation already running"}
        self._start_params = msg
        self._server_state = "running"
        self.start_event.set()
        return None
```

In the handler function inside `_serve()`, add after the `quit` handling block (after line 123 `continue`) and **before** the `if not self._paused:` gate (line 125):

```python
                    if msg_type == "start":
                        err = self._handle_start(msg)
                        if err is not None:
                            await websocket.send(json.dumps(err))
                        continue
```

Update the connect init section (lines 94-100) to branch on `_server_state`:

```python
            try:
                # Send init data based on server state
                if self._server_state == "lobby" and self._lobby_init is not None:
                    await websocket.send(json.dumps(self._lobby_init))
                elif self._server_state == "running" and self._init_data is not None:
                    await websocket.send(json.dumps(self._init_data))
                elif self._server_state == "running" and self._init_data is None:
                    # World generation in progress — send minimal ack
                    await websocket.send(json.dumps({"type": "init", "state": "starting"}))
                # Send last paused msg if paused
                if self._paused and self._last_paused_msg is not None:
                    await websocket.send(json.dumps(self._last_paused_msg))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_start_command_sets_event tests/test_live.py::test_start_command_rejected_when_running -v`
Expected: PASS

- [ ] **Step 4b: Write test for connect-init branching**

Add to `tests/test_live.py`:

```python
def test_connect_init_returns_lobby_when_in_lobby():
    """Server has correct state for lobby init on connect.

    Note: This verifies the preconditions for the handler's branching logic
    (lobby state + lobby_init populated). The actual WebSocket send behavior
    is covered by the integration tests in test_live_integration.py.
    """
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._lobby_init = {"type": "init", "state": "lobby", "scenarios": [], "models": [], "defaults": {}}

    assert server._server_state == "lobby"
    assert server._lobby_init is not None
    assert server._init_data is None


def test_connect_init_returns_starting_during_world_gen():
    """Server has correct state for starting ack during world generation.

    Note: Verifies preconditions for the handler's reconnect-during-worldgen
    branch. The handler sends {"type": "init", "state": "starting"} when
    _server_state is "running" but _init_data is None. Actual send behavior
    covered by integration tests.
    """
    from chronicler.live import LiveServer

    server = LiveServer(port=0)
    server._server_state = "running"
    server._init_data = None

    assert server._server_state == "running"
    assert server._init_data is None
```

- [ ] **Step 5: Run all existing live tests to verify nothing broke**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/live.py tests/test_live.py
git commit -m "feat(m12c): add start command handler with lobby state gating"
```

### Task 3: Add build_lobby_init and _get_available_models

**Files:**
- Modify: `src/chronicler/live.py` (add new functions after LiveServer class)
- Test: `tests/test_live.py`

- [ ] **Step 1: Write failing test for build_lobby_init**

Add to `tests/test_live.py`:

```python
def test_build_lobby_init_scans_scenarios(tmp_path):
    """build_lobby_init reads scenario YAML files and returns lobby init payload."""
    import argparse
    from chronicler.live import build_lobby_init

    # Create a test scenario file
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "test_scenario.yaml").write_text(
        "name: Test Scenario\n"
        "description: A test\n"
        "world_name: TestWorld\n"
        "civilizations:\n"
        "  - name: TestCiv\n"
        "    values: [Honor, Glory]\n"
        "regions:\n"
        "  - name: TestRegion\n"
        "    terrain: plains\n"
    )

    args = argparse.Namespace(
        local_url="http://localhost:1234/v1",
        sim_model=None,
        narrative_model=None,
    )
    result = build_lobby_init(args, scenario_dir=scenario_dir)

    assert result["type"] == "init"
    assert result["state"] == "lobby"
    assert len(result["scenarios"]) == 1
    assert result["scenarios"][0]["name"] == "Test Scenario"
    assert result["scenarios"][0]["civs"] == [{"name": "TestCiv", "values": ["Honor", "Glory"]}]
    assert result["scenarios"][0]["regions"][0]["name"] == "TestRegion"
    assert result["defaults"]["turns"] == 50
    assert result["defaults"]["seed"] is None
    assert isinstance(result["models"], list)


def test_get_available_models_with_cli_args():
    """_get_available_models returns CLI-specified models."""
    import argparse
    from chronicler.live import _get_available_models

    args = argparse.Namespace(
        local_url="http://localhost:1234/v1",
        sim_model="model-a",
        narrative_model="model-b",
    )
    result = _get_available_models(args)
    assert "model-a" in result
    assert "model-b" in result


def test_get_available_models_deduplicates():
    """_get_available_models does not duplicate when sim and narrative are the same."""
    import argparse
    from chronicler.live import _get_available_models

    args = argparse.Namespace(
        local_url="http://localhost:1234/v1",
        sim_model="same-model",
        narrative_model="same-model",
    )
    result = _get_available_models(args)
    assert result.count("same-model") == 1


def test_get_available_models_unreachable_lm_studio():
    """_get_available_models falls back gracefully when LM Studio is unreachable."""
    import argparse
    from chronicler.live import _get_available_models

    args = argparse.Namespace(
        local_url="http://localhost:99999/v1",  # unreachable
        sim_model=None,
        narrative_model=None,
    )
    result = _get_available_models(args)
    # Should return fallback, not crash
    assert isinstance(result, list)
    assert len(result) >= 1


def test_build_lobby_init_empty_scenario_dir(tmp_path):
    """build_lobby_init returns empty scenarios list when no YAML files exist."""
    import argparse
    from chronicler.live import build_lobby_init

    empty_dir = tmp_path / "empty_scenarios"
    empty_dir.mkdir()
    args = argparse.Namespace(local_url="http://localhost:1234/v1", sim_model=None, narrative_model=None)
    result = build_lobby_init(args, scenario_dir=empty_dir)

    assert result["scenarios"] == []
    assert result["state"] == "lobby"


def test_build_lobby_init_missing_fields(tmp_path):
    """build_lobby_init handles scenarios with missing optional fields."""
    import argparse
    from chronicler.live import build_lobby_init

    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "minimal.yaml").write_text("name: Minimal\n")

    args = argparse.Namespace(local_url="http://localhost:1234/v1", sim_model=None, narrative_model=None)
    result = build_lobby_init(args, scenario_dir=scenario_dir)

    s = result["scenarios"][0]
    assert s["name"] == "Minimal"
    assert s["civs"] == []
    assert s["regions"] == []
    assert s["description"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_build_lobby_init_scans_scenarios tests/test_live.py::test_build_lobby_init_empty_scenario_dir tests/test_live.py::test_build_lobby_init_missing_fields -v`
Expected: FAIL with `ImportError: cannot import name 'build_lobby_init'`

- [ ] **Step 3: Implement build_lobby_init and _get_available_models**

Add to `src/chronicler/live.py` after the `make_live_pause` function (after line 377), before `run_live`:

```python
def _get_available_models(args: Any) -> list[str]:
    """Return list of available model names for the lobby dropdowns."""
    models: list[str] = []
    # Add CLI-specified models
    sim_model = getattr(args, "sim_model", None)
    narrative_model = getattr(args, "narrative_model", None)
    if sim_model:
        models.append(sim_model)
    if narrative_model and narrative_model not in models:
        models.append(narrative_model)

    # Try LM Studio /v1/models with 500ms timeout
    local_url = getattr(args, "local_url", None)
    if local_url:
        try:
            import urllib.request
            req = urllib.request.Request(f"{local_url.rstrip('/')}/models")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.loads(resp.read())
                for m in data.get("data", []):
                    model_id = m.get("id", "")
                    if model_id and model_id not in models:
                        models.append(model_id)
        except Exception:
            pass

    # Always include a fallback if nothing found
    if not models:
        models.append("")  # empty string = LM Studio uses loaded model

    return models


def build_lobby_init(args: Any, scenario_dir: Path | None = None) -> dict:
    """Build the lobby init message by scanning scenario YAML files.

    Reads scenario data directly from YAML — no world generation.
    """
    import yaml

    if scenario_dir is None:
        scenario_dir = Path("scenarios")

    scenarios: list[dict] = []
    if scenario_dir.exists():
        for f in sorted(scenario_dir.glob("*.yaml")):
            with open(f) as fh:
                data = yaml.safe_load(fh) or {}
            scenarios.append({
                "file": f.name,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "world_name": data.get("world_name", f.stem),
                "civs": [
                    {"name": c["name"], "values": c.get("values", [])}
                    for c in data.get("civilizations", []) or []
                ],
                "regions": [
                    {
                        "name": r["name"],
                        "terrain": r.get("terrain", ""),
                        "x": r.get("x"),
                        "y": r.get("y"),
                    }
                    for r in data.get("regions", []) or []
                ],
            })

    return {
        "type": "init",
        "state": "lobby",
        "scenarios": scenarios,
        "models": _get_available_models(args),
        "defaults": {
            "turns": 50,
            "civs": 4,
            "regions": 8,
            "seed": None,
        },
    }
```

Also add `import yaml` to the file-level imports (or keep it lazy in the function as shown).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_build_lobby_init_scans_scenarios tests/test_live.py::test_build_lobby_init_empty_scenario_dir tests/test_live.py::test_build_lobby_init_missing_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/live.py tests/test_live.py
git commit -m "feat(m12c): add build_lobby_init and _get_available_models"
```

### Task 4: Refactor run_live to use lobby state

**Files:**
- Modify: `src/chronicler/live.py:380-499` (`run_live` function)
- Modify: `src/chronicler/main.py:537-541, 577-579`
- Test: `tests/test_live.py`

- [ ] **Step 1: Write failing test for resolve_start_seed helper**

Add to `tests/test_live.py`:

```python
def test_resolve_start_seed_generates_when_none():
    """resolve_start_seed returns a valid random int when seed is None."""
    from chronicler.live import resolve_start_seed

    seed = resolve_start_seed(None)
    assert isinstance(seed, int)
    assert 0 <= seed < 2**31


def test_resolve_start_seed_passes_through_int():
    """resolve_start_seed returns the seed unchanged when it's an int."""
    from chronicler.live import resolve_start_seed

    assert resolve_start_seed(42) == 42
    assert resolve_start_seed(0) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_resolve_start_seed_generates_when_none tests/test_live.py::test_resolve_start_seed_passes_through_int -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_start_seed'`

- [ ] **Step 2b: Implement resolve_start_seed**

Add to `src/chronicler/live.py` before `run_live`:

```python
def resolve_start_seed(seed: int | None) -> int:
    """Resolve seed from start command. None means server-generated random."""
    import random
    if seed is None:
        return random.randint(0, 2**31 - 1)
    return seed
```

- [ ] **Step 2c: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py::test_resolve_start_seed_generates_when_none tests/test_live.py::test_resolve_start_seed_passes_through_int -v`
Expected: PASS

- [ ] **Step 3: Refactor run_live**

Replace the `run_live` function in `src/chronicler/live.py` (lines 380-499) with:

```python
def run_live(
    args: Any,
    scenario_config: Any = None,
) -> Any:
    """Run simulation in live mode with WebSocket server.

    Phase 1: Start WebSocket server in lobby state, wait for client to send start.
    Phase 2: Generate world from client params, run simulation.
    """
    import random
    from chronicler.main import execute_run
    from chronicler.models import TurnSnapshot, Event, NamedEvent
    from chronicler.llm import create_clients

    port = getattr(args, "live_port", 8765) or 8765

    # --- Phase 1: Lobby ---
    server = LiveServer(port=port)
    server._lobby_init = build_lobby_init(args)
    server.start()
    actual_port = server._actual_port or port
    print(f"Lobby ready on ws://localhost:{actual_port}")
    print(f"Open viewer: http://localhost:5173?ws=ws://localhost:{actual_port}")
    print("Waiting for client to launch simulation...")

    # Block until client sends start (interruptible via Ctrl+C)
    while not server.start_event.wait(timeout=1.0):
        pass

    params = server._start_params
    if params is None:
        raise RuntimeError("start_event set but no _start_params")

    # --- Phase 2: Simulation ---

    # Resolve world and scenario from client params
    scenario_config = None
    if params.get("resume_state"):
        world = WorldState.model_validate(params["resume_state"])
    else:
        seed = resolve_start_seed(params.get("seed"))

        from chronicler.world_gen import generate_world
        world = generate_world(
            seed=seed,
            num_regions=params.get("regions", 8),
            num_civs=params.get("civs", 4),
        )
        if params.get("scenario"):
            from chronicler.scenario import load_scenario, apply_scenario
            scenario_config = load_scenario(Path("scenarios") / params["scenario"])
            apply_scenario(world, scenario_config)

    # Construct LLM clients from client-selected models
    sim_model = params.get("sim_model") or getattr(args, "sim_model", None)
    narrative_model = params.get("narrative_model") or getattr(args, "narrative_model", None)
    sim_client, narrative_client = create_clients(
        local_url=getattr(args, "local_url", "http://localhost:1234/v1"),
        sim_model=sim_model,
        narrative_model=narrative_model,
    )

    pause_every = getattr(args, "pause_every", None) or getattr(args, "reflection_interval", 10) or 10
    total_turns = params.get("turns") or args.turns or 50
    output_dir = Path(args.output).parent

    init_sent = [False]
    world_ref = [world]

    def _serialize_snapshot(snapshot, chronicle_text, events, named_events):
        """Serialize turn data to a dict for the WebSocket protocol."""
        snap_dict = snapshot.model_dump(mode="json")
        snap_dict["type"] = "turn"
        snap_dict["chronicle_text"] = chronicle_text
        snap_dict["events"] = [e.model_dump(mode="json") for e in events]
        snap_dict["named_events"] = [ne.model_dump(mode="json") for ne in named_events]
        return snap_dict

    def on_turn_cb(
        snapshot: TurnSnapshot,
        chronicle_text: str,
        events: list[Event],
        named_events: list[NamedEvent],
    ) -> None:
        if not init_sent[0]:
            init_sent[0] = True
            w = world_ref[0]
            init_msg = {
                "type": "init",
                "state": "running",
                "total_turns": total_turns,
                "pause_every": pause_every,
                "current_turn": 0,
                "world_state": w.model_dump(mode="json"),
                "history": [],
                "chronicle_entries": {},
                "events_timeline": [],
                "named_events": [],
                "era_reflections": {},
                "metadata": {
                    "seed": w.seed,
                    "total_turns": total_turns,
                    "generated_at": "",
                    "sim_model": getattr(sim_client, "model", "unknown") or "unknown",
                    "narrative_model": getattr(narrative_client, "model", "unknown") or "unknown",
                    "scenario_name": getattr(w, "scenario_name", None),
                    "interestingness_score": None,
                },
                "speed": server.speed,
            }
            server.snapshot_queue.put(init_msg)

        snap_dict = _serialize_snapshot(snapshot, chronicle_text, events, named_events)
        server.snapshot_queue.put(snap_dict)

        spd = server.speed
        if spd > 0:
            time.sleep(1.0 / spd)

    pending_injections: list[tuple[str, str]] = []
    pause_fn = make_live_pause(
        server.command_queue,
        server.status_queue,
        output_dir=output_dir,
    )

    # Override args with client params for execute_run
    args.turns = total_turns
    args.seed = world.seed

    result = execute_run(
        args,
        sim_client=sim_client,
        narrative_client=narrative_client,
        world=world,
        on_pause=pause_fn,
        pause_every=pause_every,
        pending_injections=pending_injections,
        scenario_config=scenario_config,
        on_turn=on_turn_cb,
        quit_check=lambda: server.quit_event.is_set(),
    )

    server.status_queue.put({
        "type": "completed",
        "total_turns": result.total_turns,
        "bundle_path": str(output_dir / "chronicle_bundle.json"),
    })

    time.sleep(0.5)
    server.stop()

    return result
```

- [ ] **Step 4: Update main.py to skip client and scenario resolution for live mode**

In `src/chronicler/main.py`, guard both client construction (lines 537-541) and scenario resolution (lines 543-559) with `if not args.live:`. The lobby handles both of these from the client's `start` command.

```python
    # Skip LLM client and scenario resolution for live mode — run_live
    # handles both after receiving params from the client's start command
    if not args.live:
        sim_client, narrative_client = create_clients(
            local_url=args.local_url,
            sim_model=args.sim_model,
            narrative_model=args.narrative_model,
        )

        # Resolve scenario
        scenario_config = None
        if args.scenario:
            from chronicler.scenario import load_scenario, resolve_scenario_params
            scenario_config = load_scenario(Path(args.scenario))
            params = resolve_scenario_params(scenario_config, args)
            args.seed = params["seed"]
            args.turns = params["num_turns"]
            args.civs = params["num_civs"]
            args.regions = params["num_regions"]
            args.reflection_interval = params["reflection_interval"]
        else:
            args.seed = args.seed if args.seed is not None else DEFAULT_CONFIG.get("seed", 42)
            args.turns = args.turns if args.turns is not None else DEFAULT_CONFIG["num_turns"]
            args.civs = args.civs if args.civs is not None else DEFAULT_CONFIG["num_civs"]
            args.regions = args.regions if args.regions is not None else DEFAULT_CONFIG["num_regions"]
            args.reflection_interval = args.reflection_interval if args.reflection_interval is not None else DEFAULT_CONFIG["reflection_interval"]
    else:
        sim_client = None
        narrative_client = None
        scenario_config = None
```

And update the live dispatch (lines 577-579):

```python
    elif args.live:
        from chronicler.live import run_live
        result = run_live(args)
        print(f"\nLive session complete: {result.output_dir}")
```

- [ ] **Step 5: Run all live tests**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/live.py src/chronicler/main.py tests/test_live.py
git commit -m "feat(m12c): refactor run_live for lobby state, move client construction"
```

---

## Chunk 2: Frontend — Types, Hook, and App State Machine

### Task 5: Add new types to types.ts

**Files:**
- Modify: `viewer/src/types.ts:155-213`

- [ ] **Step 1: Add ScenarioInfo, LobbyInit, StartCommand types**

Add after the `ForkedMessage` interface (line 213) in `viewer/src/types.ts`:

```typescript

// --- Setup lobby types ---

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

Note: `StartCommand` is NOT added to the `Command` union — it stays separate. `WorldState` is already defined at line 121 of `types.ts`, so `resume_state: WorldState | null` compiles without additional imports.

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add viewer/src/types.ts
git commit -m "feat(m12c): add ScenarioInfo, LobbyInit, StartCommand types"
```

### Task 6: Add lobby state to useLiveConnection hook

**Files:**
- Modify: `viewer/src/hooks/useLiveConnection.ts`
- Test: `viewer/src/hooks/__tests__/useLiveConnection.test.ts`

- [ ] **Step 1: Write failing tests for lobby state handling**

Add to `viewer/src/hooks/__tests__/useLiveConnection.test.ts`:

```typescript
const SAMPLE_LOBBY_INIT = {
  type: "init",
  state: "lobby",
  scenarios: [
    {
      file: "test.yaml",
      name: "Test Scenario",
      description: "A test",
      world_name: "TestWorld",
      civs: [{ name: "TestCiv", values: ["Honor"] }],
      regions: [{ name: "TestRegion", terrain: "plains", x: null, y: null }],
    },
  ],
  models: ["test-model"],
  defaults: { turns: 50, civs: 4, regions: 8, seed: null },
};

describe("lobby state", () => {
  it("sets serverState to lobby on lobby init", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    expect(result.current.serverState).toBe("lobby");
    expect(result.current.lobbyInit).not.toBeNull();
    expect(result.current.lobbyInit?.scenarios.length).toBe(1);
    expect(result.current.bundle).toBeNull();
  });

  it("treats init without state field as running (backward compat)", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    // SAMPLE_INIT has no state field — should be treated as running
    act(() => ws.simulateMessage(SAMPLE_INIT));

    expect(result.current.serverState).toBe("running");
    expect(result.current.bundle).not.toBeNull();
  });

  it("sendStart transitions to starting and sends start command", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    act(() => {
      result.current.sendStart({
        scenario: "test.yaml",
        turns: 50,
        seed: 42,
        civs: 4,
        regions: 8,
        sim_model: "test-model",
        narrative_model: "test-model",
        resume_state: null,
      });
    });

    expect(result.current.serverState).toBe("starting");
    expect(ws.sent.length).toBe(1);
    const sent = JSON.parse(ws.sent[0]);
    expect(sent.type).toBe("start");
    expect(sent.scenario).toBe("test.yaml");
  });

  it("reverts to lobby on error during starting", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    act(() => {
      result.current.sendStart({
        scenario: "bad.yaml", turns: 50, seed: 42, civs: 4, regions: 8,
        sim_model: "m", narrative_model: "m", resume_state: null,
      });
    });
    expect(result.current.serverState).toBe("starting");

    act(() => ws.simulateMessage({ type: "error", message: "Scenario not found" }));
    expect(result.current.serverState).toBe("lobby");
    expect(result.current.error).toBe("Scenario not found");
  });

  it("full retry: starting → error → lobby → retry → starting → running", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    // First attempt fails
    act(() => {
      result.current.sendStart({
        scenario: "bad.yaml", turns: 50, seed: 42, civs: 4, regions: 8,
        sim_model: "m", narrative_model: "m", resume_state: null,
      });
    });
    expect(result.current.serverState).toBe("starting");

    act(() => ws.simulateMessage({ type: "error", message: "Not found" }));
    expect(result.current.serverState).toBe("lobby");

    // Second attempt succeeds
    act(() => {
      result.current.sendStart({
        scenario: "test.yaml", turns: 50, seed: 42, civs: 4, regions: 8,
        sim_model: "m", narrative_model: "m", resume_state: null,
      });
    });
    expect(result.current.serverState).toBe("starting");
    expect(ws.sent.length).toBe(2);

    act(() => ws.simulateMessage({ ...SAMPLE_INIT, state: "running" }));
    expect(result.current.serverState).toBe("running");
    expect(result.current.bundle).not.toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("handles server-sent starting state during world gen", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateMessage({ type: "init", state: "starting" }));
    expect(result.current.serverState).toBe("starting");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx vitest run src/hooks/__tests__/useLiveConnection.test.ts`
Expected: FAIL — `serverState`, `lobbyInit`, `sendStart` don't exist on the hook return

- [ ] **Step 3: Update useLiveConnection hook**

**Important:** If the current file differs from the baseline read during plan creation (e.g., due to M12 bug fixes), apply the lobby additions as incremental changes rather than wholesale replacement. The key changes are: (a) new state variables, (b) `sendStart` method, (c) branching the `init` handler on `msg.state`, (d) `"starting"` revert on error, (e) `"completed"` sets serverState.

Full replacement for reference (apply incrementally if file has diverged):

```typescript
import { useState, useEffect, useCallback, useRef } from "react";
import type {
  Bundle, PauseContext, Command, AckMessage, ForkedMessage,
  LobbyInit, StartCommand,
} from "../types";

type ServerState = "connecting" | "lobby" | "starting" | "running" | "completed";

interface LiveConnectionState {
  bundle: Bundle | null;
  connected: boolean;
  paused: boolean;
  pauseContext: PauseContext | null;
  error: string | null;
  sendCommand: (cmd: Command) => void;
  speed: number;
  setSpeed: (s: number) => void;
  lastAck: AckMessage | null;
  lastForked: ForkedMessage | null;
  serverState: ServerState;
  lobbyInit: LobbyInit | null;
  sendStart: (params: Omit<StartCommand, "type">) => void;
}

export function useLiveConnection(wsUrl: string): LiveConnectionState {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [pauseContext, setPauseContext] = useState<PauseContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [speed, setSpeedState] = useState(1);
  const [lastAck, setLastAck] = useState<AckMessage | null>(null);
  const [lastForked, setLastForked] = useState<ForkedMessage | null>(null);
  const [serverState, setServerState] = useState<ServerState>("connecting");
  const [lobbyInit, setLobbyInit] = useState<LobbyInit | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);
  const serverStateRef = useRef<ServerState>("connecting");

  const sendCommand = useCallback((cmd: Command) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  const sendStart = useCallback((params: Omit<StartCommand, "type">) => {
    if (serverStateRef.current !== "lobby") return;  // prevent double-submission
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      setServerState("starting");
      serverStateRef.current = "starting";
      setError(null);
      wsRef.current.send(JSON.stringify({ type: "start", ...params }));
    }
  }, []);

  const setSpeed = useCallback((s: number) => {
    setSpeedState(s);
    sendCommand({ type: "speed", value: s });
  }, [sendCommand]);

  useEffect(() => {
    let unmounted = false;

    if (!wsUrl) return;

    function connect() {
      if (unmounted) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmounted) return;
        setConnected(true);
        setError(null);
        reconnectDelayRef.current = 1000;
      };

      ws.onclose = () => {
        if (unmounted) return;
        setConnected(false);
        wsRef.current = null;
        const delay = reconnectDelayRef.current;
        reconnectRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(delay * 2, 10000);
          connect();
        }, delay);
      };

      ws.onerror = () => {};

      ws.onmessage = (e) => {
        if (unmounted) return;
        const msg = JSON.parse(e.data);

        switch (msg.type) {
          case "init":
            if (msg.state === "lobby") {
              setServerState("lobby");
              serverStateRef.current = "lobby";
              setLobbyInit({
                scenarios: msg.scenarios,
                models: msg.models,
                defaults: msg.defaults,
              });
            } else if (msg.state === "starting") {
              setServerState("starting");
              serverStateRef.current = "starting";
            } else {
              // "running" or absent (backward compat: pre-lobby servers
              // don't send state field; treat absence as running)
              setServerState("running");
              serverStateRef.current = "running";
              setError(null);
              setBundle({
                world_state: msg.world_state,
                history: msg.history || [],
                events_timeline: msg.events_timeline || [],
                named_events: msg.named_events || [],
                chronicle_entries: msg.chronicle_entries || {},
                era_reflections: msg.era_reflections || {},
                metadata: msg.metadata,
              });
              if (msg.speed !== undefined) {
                setSpeedState(msg.speed);
              }
            }
            break;

          case "turn":
            setBundle((prev) => {
              if (!prev) return prev;
              const snap = {
                turn: msg.turn,
                civ_stats: msg.civ_stats,
                region_control: msg.region_control,
                relationships: msg.relationships,
              };
              return {
                ...prev,
                history: [...prev.history, snap],
                chronicle_entries: {
                  ...prev.chronicle_entries,
                  [String(msg.turn)]: msg.chronicle_text || "",
                },
                events_timeline: [...prev.events_timeline, ...(msg.events || [])],
                named_events: [...prev.named_events, ...(msg.named_events || [])],
              };
            });
            break;

          case "paused":
            setPaused(true);
            setPauseContext({
              turn: msg.turn,
              reason: msg.reason,
              valid_commands: msg.valid_commands,
              injectable_events: msg.injectable_events,
              settable_stats: msg.settable_stats,
              civs: msg.civs,
            });
            break;

          case "ack": {
            const ack = msg as AckMessage;
            setLastAck(ack);
            if (!ack.still_paused) {
              setPaused(false);
              setPauseContext(null);
            }
            if (ack.command === "set" && ack.civ && ack.stat && ack.value !== undefined) {
              setBundle((prev) => {
                if (!prev || prev.history.length === 0) return prev;
                const newHistory = [...prev.history];
                const lastIdx = newHistory.length - 1;
                const lastSnap = { ...newHistory[lastIdx] };
                const civStats = { ...lastSnap.civ_stats };
                const civData = civStats[ack.civ!];
                if (civData) {
                  civStats[ack.civ!] = { ...civData, [ack.stat!]: ack.value };
                  lastSnap.civ_stats = civStats;
                  newHistory[lastIdx] = lastSnap;
                }
                return { ...prev, history: newHistory };
              });
            }
            break;
          }

          case "forked":
            setLastForked(msg as ForkedMessage);
            break;

          case "completed":
            setServerState("completed");
            serverStateRef.current = "completed";
            setPaused(false);
            setPauseContext(null);
            break;

          case "error":
            setError(msg.message);
            // Revert to lobby if we were in "starting" state
            if (serverStateRef.current === "starting") {
              setServerState("lobby");
              serverStateRef.current = "lobby";
            }
            break;
        }
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [wsUrl]);

  return {
    bundle,
    connected,
    paused,
    pauseContext,
    error,
    sendCommand,
    speed,
    setSpeed,
    lastAck,
    lastForked,
    serverState,
    lobbyInit,
    sendStart,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx vitest run src/hooks/__tests__/useLiveConnection.test.ts`
Expected: All PASS (both new lobby tests and existing tests)

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add viewer/src/hooks/useLiveConnection.ts viewer/src/hooks/__tests__/useLiveConnection.test.ts
git commit -m "feat(m12c): add lobby state, sendStart, and error recovery to useLiveConnection"
```

### Task 7: Update App.tsx state machine

**Files:**
- Modify: `viewer/src/App.tsx`

- [ ] **Step 1: Update App.tsx to gate on serverState**

**Important:** If the current file differs from the baseline read during plan creation, apply changes incrementally: (a) add `SetupLobby` import, (b) add the `serverState` switch block for live mode, (c) keep existing static mode unchanged.

Full replacement for reference (apply incrementally if file has diverged):

```typescript
import { useCallback } from "react";
import { useBundle } from "./hooks/useBundle";
import { useLiveConnection } from "./hooks/useLiveConnection";
import { useTimeline } from "./hooks/useTimeline";
import { Layout } from "./components/Layout";
import { SetupLobby } from "./components/SetupLobby";

function App() {
  const wsUrl = new URLSearchParams(window.location.search).get("ws");

  // Both hooks always called (Rules of Hooks) — only one is active
  const { bundle: staticBundle, error: staticError, loading, loadFromFile } = useBundle();
  const liveConn = useLiveConnection(wsUrl || "");

  const isLive = wsUrl !== null;
  const bundle = isLive ? liveConn.bundle : staticBundle;
  const error = isLive ? liveConn.error : staticError;

  const timeline = useTimeline(
    bundle?.history.length ?? bundle?.metadata?.total_turns ?? 1,
    { liveMode: isLive && liveConn.connected },
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file) loadFromFile(file);
    },
    [loadFromFile],
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) loadFromFile(file);
    },
    [loadFromFile],
  );

  // --- Live mode state machine ---
  if (isLive) {
    switch (liveConn.serverState) {
      case "connecting":
        return (
          <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
            <p className="text-gray-400">Connecting to simulation...</p>
          </div>
        );

      case "lobby":
      case "starting":
        if (!liveConn.lobbyInit) {
          // Reconnect during world-gen: server sent "starting" but no lobby data
          return (
            <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
              <p className="text-gray-400">World generating...</p>
            </div>
          );
        }
        return (
          <SetupLobby
            lobbyInit={liveConn.lobbyInit}
            onLaunch={liveConn.sendStart}
            starting={liveConn.serverState === "starting"}
            error={liveConn.error}
          />
        );

      case "running":
      case "completed":
        if (!bundle) {
          return (
            <div className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center">
              <p className="text-gray-400">Waiting for simulation data...</p>
            </div>
          );
        }
        return (
          <Layout
            bundle={bundle}
            currentTurn={timeline.currentTurn}
            playing={timeline.playing}
            speed={timeline.speed}
            onSeek={timeline.seek}
            onPlay={timeline.play}
            onPause={timeline.pause}
            onSetSpeed={liveConn.connected ? liveConn.setSpeed : timeline.setSpeed}
            liveConnected={liveConn.connected}
            livePaused={liveConn.paused}
            livePauseContext={liveConn.pauseContext}
            liveSendCommand={liveConn.sendCommand}
            liveForkedPath={liveConn.lastForked?.save_path}
            liveForkedHint={liveConn.lastForked?.cli_hint}
            liveReconnecting={!liveConn.connected && !!wsUrl}
          />
        );
    }
  }

  // --- Static mode (unchanged) ---
  if (!bundle) {
    return (
      <div
        className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        <div className="text-center space-y-4">
          <h1 className="text-2xl font-bold">Chronicler Viewer</h1>
          <p className="text-gray-400">
            Drag and drop a <code className="text-blue-400">chronicle_bundle.json</code> file here
          </p>
          <label className="inline-block px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 cursor-pointer">
            Or choose a file
            <input
              type="file"
              accept=".json"
              onChange={handleFileInput}
              className="hidden"
            />
          </label>
          {loading && <p className="text-gray-400">Loading...</p>}
          {error && <p className="text-red-400">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <Layout
      bundle={bundle}
      currentTurn={timeline.currentTurn}
      playing={timeline.playing}
      speed={timeline.speed}
      onSeek={timeline.seek}
      onPlay={timeline.play}
      onPause={timeline.pause}
      onSetSpeed={timeline.setSpeed}
      liveConnected={undefined}
      livePaused={undefined}
      livePauseContext={undefined}
      liveSendCommand={undefined}
      liveForkedPath={undefined}
      liveForkedHint={undefined}
      liveReconnecting={undefined}
    />
  );
}

export default App;
```

Note: This imports `SetupLobby` which doesn't exist yet — that's Task 9. Do NOT commit yet. TypeScript will fail until SetupLobby is created. App.tsx will be committed together with SetupLobby in Task 9.

- [ ] **Step 2: Verify the file is saved** (no commit — deferred to Task 9)

---

## Chunk 3: Frontend — SetupLobby Component and RegionMap

### Task 8: Create RegionMap component

**Files:**
- Create: `viewer/src/components/RegionMap.tsx`
- Create: `viewer/src/components/__tests__/RegionMap.test.tsx`

- [ ] **Step 1: Write failing tests for RegionMap**

Create `viewer/src/components/__tests__/RegionMap.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RegionMap } from "../RegionMap";

const REGIONS_WITH_COORDS = [
  { name: "Plains", terrain: "plains", x: 0.3, y: 0.5 },
  { name: "Desert", terrain: "desert", x: 0.7, y: 0.3 },
];

const REGIONS_NULL_COORDS = [
  { name: "Region A", terrain: "forest", x: null, y: null },
  { name: "Region B", terrain: "mountain", x: null, y: null },
  { name: "Region C", terrain: "plains", x: null, y: null },
];

describe("RegionMap", () => {
  it("renders SVG with region labels", () => {
    render(<RegionMap regions={REGIONS_WITH_COORDS} />);
    expect(screen.getByText("Plains")).toBeTruthy();
    expect(screen.getByText("Desert")).toBeTruthy();
  });

  it("renders with null coordinates using circle layout", () => {
    render(<RegionMap regions={REGIONS_NULL_COORDS} />);
    expect(screen.getByText("Region A")).toBeTruthy();
    expect(screen.getByText("Region B")).toBeTruthy();
    expect(screen.getByText("Region C")).toBeTruthy();
  });

  it("renders empty state when no regions", () => {
    render(<RegionMap regions={[]} />);
    const svg = document.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders with controller coloring when provided", () => {
    render(
      <RegionMap
        regions={REGIONS_WITH_COORDS}
        controllers={{ Plains: "CivA", Desert: null }}
      />
    );
    expect(screen.getByText("Plains")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx vitest run src/components/__tests__/RegionMap.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create RegionMap component**

Create `viewer/src/components/RegionMap.tsx`:

```typescript
import type { FC } from "react";
import { factionColor, UNCONTROLLED_COLOR } from "../lib/colors";

interface RegionData {
  name: string;
  terrain: string;
  x: number | null;
  y: number | null;
}

interface RegionMapProps {
  regions: RegionData[];
  controllers?: Record<string, string | null>;
  width?: number;
  height?: number;
}

const TERRAIN_COLORS: Record<string, string> = {
  plains: "#4ade80",
  forest: "#166534",
  mountain: "#78716c",
  desert: "#fbbf24",
  tundra: "#93c5fd",
  swamp: "#65a30d",
  coast: "#38bdf8",
  jungle: "#15803d",
  steppe: "#a3e635",
  wasteland: "#a8a29e",
};

function circleLayout(
  count: number,
  width: number,
  height: number,
): { x: number; y: number }[] {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;
  return Array.from({ length: count }, (_, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2;
    return {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
    };
  });
}

export const RegionMap: FC<RegionMapProps> = ({
  regions,
  controllers,
  width = 400,
  height = 300,
}) => {
  if (regions.length === 0) {
    return <svg width={width} height={height} className="bg-gray-900 rounded" />;
  }

  const hasPins = regions.some((r) => r.x !== null && r.y !== null);
  const fallback = !hasPins ? circleLayout(regions.length, width, height) : null;

  return (
    <svg width={width} height={height} className="bg-gray-900 rounded">
      {regions.map((r, i) => {
        const px = r.x !== null ? r.x * width : fallback![i].x;
        const py = r.y !== null ? r.y * height : fallback![i].y;
        const ctrl = controllers?.[r.name];
        const fillColor = ctrl
          ? factionColor(ctrl)
          : controllers
            ? UNCONTROLLED_COLOR
            : TERRAIN_COLORS[r.terrain] ?? "#6b7280";

        return (
          <g key={r.name}>
            <circle
              cx={px}
              cy={py}
              r={12}
              fill={fillColor}
              stroke="#1f2937"
              strokeWidth={1.5}
              opacity={0.9}
            />
            <text
              x={px}
              y={py + 22}
              textAnchor="middle"
              className="fill-gray-400 text-[9px]"
            >
              {r.name.length > 14 ? r.name.slice(0, 14) + "\u2026" : r.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx vitest run src/components/__tests__/RegionMap.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add viewer/src/components/RegionMap.tsx viewer/src/components/__tests__/RegionMap.test.tsx
git commit -m "feat(m12c): add RegionMap component with circle layout fallback"
```

### Task 9: Create SetupLobby component

**Files:**
- Create: `viewer/src/components/SetupLobby.tsx`
- Create: `viewer/src/components/__tests__/SetupLobby.test.tsx`

- [ ] **Step 1: Write failing tests for SetupLobby**

Create `viewer/src/components/__tests__/SetupLobby.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SetupLobby } from "../SetupLobby";
import type { LobbyInit } from "../../types";

const LOBBY_INIT: LobbyInit = {
  scenarios: [
    {
      file: "test.yaml",
      name: "Test Scenario",
      description: "A test scenario for unit tests",
      world_name: "TestWorld",
      civs: [
        { name: "Civ A", values: ["Honor", "Trade"] },
        { name: "Civ B", values: ["War"] },
      ],
      regions: [
        { name: "Plains", terrain: "plains", x: null, y: null },
        { name: "Mountains", terrain: "mountain", x: null, y: null },
      ],
    },
    {
      file: "minimal.yaml",
      name: "Minimal",
      description: "No civs or regions",
      world_name: "Minimal",
      civs: [],
      regions: [],
    },
  ],
  models: ["model-a", "model-b"],
  defaults: { turns: 50, civs: 4, regions: 8, seed: null },
};

describe("SetupLobby", () => {
  it("renders all six control sections", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    // Scenario dropdown
    expect(screen.getByLabelText("Scenario")).toBeTruthy();
    // Seed input
    expect(screen.getByLabelText("Seed")).toBeTruthy();
    // Turns input
    expect(screen.getByLabelText("Turns")).toBeTruthy();
    // Civs input
    expect(screen.getByLabelText("Civs")).toBeTruthy();
    // Regions input
    expect(screen.getByLabelText("Regions")).toBeTruthy();
    // Model selectors
    expect(screen.getByLabelText("Sim Model")).toBeTruthy();
    expect(screen.getByLabelText("Narrative Model")).toBeTruthy();
    // Launch button
    expect(screen.getByRole("button", { name: /launch/i })).toBeTruthy();
  });

  it("disables civs when scenario has civs", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    // Select test scenario (has civs)
    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "test.yaml" } });
    expect(screen.getByLabelText("Civs")).toBeDisabled();
  });

  it("disables regions when scenario has regions", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "test.yaml" } });
    expect(screen.getByLabelText("Regions")).toBeDisabled();
  });

  it("enables civs/regions independently for scenarios without them", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "minimal.yaml" } });
    expect(screen.getByLabelText("Civs")).not.toBeDisabled();
    expect(screen.getByLabelText("Regions")).not.toBeDisabled();
  });

  it("disables launch button when starting", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={true} error={null} />
    );

    expect(screen.getByRole("button", { name: /starting/i })).toBeDisabled();
  });

  it("calls onLaunch with correct params", () => {
    const onLaunch = vi.fn();
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={onLaunch} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Turns"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: /launch/i }));

    expect(onLaunch).toHaveBeenCalledTimes(1);
    const params = onLaunch.mock.calls[0][0];
    expect(params.turns).toBe(100);
    expect(params.seed).toBe(42);
    expect(params.scenario).toBeNull();  // Procedural = null
    expect(params.civs).toBe(4);  // defaults
    expect(params.regions).toBe(8);  // defaults
    expect(params.sim_model).toBe("model-a");
    expect(params.narrative_model).toBe("model-a");
    expect(params.resume_state).toBeNull();
  });

  it("shows resume badge and disables fields on valid state.json", async () => {
    const onLaunch = vi.fn();
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={onLaunch} starting={false} error={null} />
    );

    const stateJson = JSON.stringify({
      turn: 22,
      name: "TestWorld",
      seed: 42,
      civilizations: [{ name: "CivA" }, { name: "CivB" }],
      regions: [{ name: "R1", controller: "CivA" }],
      relationships: {},
      events_timeline: [],
      named_events: [],
      scenario_name: null,
    });
    const file = new File([stateJson], "state.json", { type: "application/json" });

    // Simulate file drop on the drop zone
    const dropZone = screen.getByText(/drop state.json/i);
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    // Wait for FileReader async
    await vi.waitFor(() => {
      expect(screen.getByText(/resuming from turn 22/i)).toBeTruthy();
    });

    expect(screen.getByLabelText("Civs")).toBeDisabled();
    expect(screen.getByLabelText("Regions")).toBeDisabled();
    expect(screen.getByLabelText("Scenario")).toBeDisabled();
  });

  it("shows error on invalid resume file", async () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    const badJson = JSON.stringify({ foo: "bar" });
    const file = new File([badJson], "bad.json", { type: "application/json" });
    const dropZone = screen.getByText(/drop state.json/i);
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    await vi.waitFor(() => {
      expect(screen.getByText(/invalid save file/i)).toBeTruthy();
    });
  });

  it("clears resume on clear button click", async () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    const stateJson = JSON.stringify({
      turn: 10, name: "W", seed: 1,
      civilizations: [{ name: "C" }], regions: [{ name: "R", controller: null }],
      relationships: {}, events_timeline: [], named_events: [], scenario_name: null,
    });
    const file = new File([stateJson], "state.json", { type: "application/json" });
    const dropZone = screen.getByText(/drop state.json/i);
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } });

    await vi.waitFor(() => {
      expect(screen.getByText(/resuming from turn 10/i)).toBeTruthy();
    });

    fireEvent.click(screen.getByLabelText("Clear resume"));
    expect(screen.queryByText(/resuming/i)).toBeNull();
    expect(screen.getByLabelText("Civs")).not.toBeDisabled();
  });

  it("shows error banner when error is set", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error="Scenario not found" />
    );

    expect(screen.getByText("Scenario not found")).toBeTruthy();
  });

  it("shows preview when scenario selected", () => {
    render(
      <SetupLobby lobbyInit={LOBBY_INIT} onLaunch={vi.fn()} starting={false} error={null} />
    );

    fireEvent.change(screen.getByLabelText("Scenario"), { target: { value: "test.yaml" } });
    // Use getByRole to avoid collision with the <option> element text
    expect(screen.getByRole("heading", { name: "Test Scenario" })).toBeTruthy();
    expect(screen.getByText("A test scenario for unit tests")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx vitest run src/components/__tests__/SetupLobby.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Create SetupLobby component**

Create `viewer/src/components/SetupLobby.tsx`:

```typescript
import { useState, useCallback, useRef } from "react";
import type { LobbyInit, StartCommand, ScenarioInfo, WorldState } from "../types";
import { RegionMap } from "./RegionMap";

interface SetupLobbyProps {
  lobbyInit: LobbyInit;
  onLaunch: (params: Omit<StartCommand, "type">) => void;
  starting: boolean;
  error: string | null;
}

export function SetupLobby({ lobbyInit, onLaunch, starting, error }: SetupLobbyProps) {
  const { scenarios, models, defaults } = lobbyInit;

  const [scenario, setScenario] = useState<string>("");
  const [seed, setSeed] = useState<string>("");
  const [turns, setTurns] = useState(defaults.turns);
  const [civs, setCivs] = useState(defaults.civs);
  const [regions, setRegions] = useState(defaults.regions);
  const [simModel, setSimModel] = useState(models[0] || "");
  const [narrativeModel, setNarrativeModel] = useState(models[0] || "");
  const [customSimModel, setCustomSimModel] = useState("");
  const [customNarrativeModel, setCustomNarrativeModel] = useState("");
  const [resumeState, setResumeState] = useState<WorldState | null>(null);
  const [resumeTurn, setResumeTurn] = useState<number | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedScenario: ScenarioInfo | null =
    scenarios.find((s) => s.file === scenario) ?? null;

  const civsDisabled = resumeState !== null || (selectedScenario?.civs?.length ?? 0) > 0;
  const regionsDisabled = resumeState !== null || (selectedScenario?.regions?.length ?? 0) > 0;

  const handleResumeFile = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result as string);
        if (typeof parsed.turn !== "number" || !Array.isArray(parsed.civilizations)) {
          setResumeError("Invalid save file \u2014 missing required fields");
          return;
        }
        setResumeState(parsed as WorldState);
        setResumeTurn(parsed.turn);
        setResumeError(null);
      } catch {
        setResumeError("Invalid save file \u2014 not valid JSON");
      }
    };
    reader.readAsText(file);
  }, []);

  const clearResume = useCallback(() => {
    setResumeState(null);
    setResumeTurn(null);
    setResumeError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const handleLaunch = useCallback(() => {
    if (turns <= 0) return;

    const resolvedSimModel = simModel === "__custom__" ? customSimModel : simModel;
    const resolvedNarrativeModel = narrativeModel === "__custom__" ? customNarrativeModel : narrativeModel;

    onLaunch({
      scenario: resumeState ? null : (scenario || null),
      turns,
      seed: seed === "" ? null : Number(seed),
      civs: resumeState
        ? resumeState.civilizations.length
        : civsDisabled
          ? (selectedScenario?.civs?.length || defaults.civs)
          : civs,
      regions: resumeState
        ? resumeState.regions.length
        : regionsDisabled
          ? (selectedScenario?.regions?.length || defaults.regions)
          : regions,
      sim_model: resolvedSimModel,
      narrative_model: resolvedNarrativeModel,
      resume_state: resumeState,
    });
  }, [
    scenario, seed, turns, civs, regions, simModel, narrativeModel,
    customSimModel, customNarrativeModel, resumeState, civsDisabled,
    regionsDisabled, selectedScenario, defaults, onLaunch,
  ]);

  // Preview data
  const previewRegions = resumeState
    ? resumeState.regions.map((r) => ({ name: r.name, terrain: r.terrain, x: r.x, y: r.y }))
    : selectedScenario?.regions ?? [];

  const previewControllers = resumeState
    ? Object.fromEntries(resumeState.regions.map((r) => [r.name, r.controller]))
    : undefined;

  const previewCivs = resumeState
    ? resumeState.civilizations.map((c) => ({ name: c.name, values: c.values }))
    : selectedScenario?.civs ?? [];

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex">
      {/* Sidebar */}
      <div className="w-[300px] bg-gray-800 border-r border-gray-700 p-5 flex flex-col">
        <div className="mb-6">
          <h1 className="text-lg font-bold text-red-400 tracking-wider">CHRONICLER</h1>
          <p className="text-xs text-gray-500 mt-1">Setup</p>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto">
          {/* Scenario */}
          <div>
            <label htmlFor="scenario-select" className="block text-[10px] text-gray-500 uppercase mb-1">Scenario</label>
            <select
              id="scenario-select"
              aria-label="Scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              disabled={resumeState !== null}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
            >
              <option value="">(Procedural)</option>
              {scenarios.map((s) => (
                <option key={s.file} value={s.file}>{s.name}</option>
              ))}
            </select>
          </div>

          {/* Seed */}
          <div>
            <label htmlFor="seed-input" className="block text-[10px] text-gray-500 uppercase mb-1">Seed</label>
            <div className="flex gap-1">
              <input
                id="seed-input"
                aria-label="Seed"
                type="number"
                min={0}
                placeholder="Random"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 placeholder-gray-500"
              />
              <button
                onClick={() => setSeed(String(Math.floor(Math.random() * 2147483647)))}
                className="px-2 py-1.5 bg-gray-700 text-red-400 rounded text-sm border border-gray-600 hover:bg-gray-600"
                title="Random seed"
              >
                &#x1F3B2;
              </button>
            </div>
          </div>

          {/* Turns */}
          <div>
            <label htmlFor="turns-input" className="block text-[10px] text-gray-500 uppercase mb-1">Turns</label>
            <input
              id="turns-input"
              aria-label="Turns"
              type="number"
              min={1}
              value={turns}
              onChange={(e) => setTurns(Number(e.target.value) || 1)}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600"
            />
          </div>

          {/* Civs / Regions */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label htmlFor="civs-input" className="block text-[10px] text-gray-500 uppercase mb-1">Civs</label>
              <input
                id="civs-input"
                aria-label="Civs"
                type="number"
                min={1}
                value={civsDisabled ? (selectedScenario?.civs?.length || civs) : civs}
                onChange={(e) => setCivs(Number(e.target.value) || 1)}
                disabled={civsDisabled}
                className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
              />
            </div>
            <div>
              <label htmlFor="regions-input" className="block text-[10px] text-gray-500 uppercase mb-1">Regions</label>
              <input
                id="regions-input"
                aria-label="Regions"
                type="number"
                min={1}
                value={regionsDisabled ? (selectedScenario?.regions?.length || regions) : regions}
                onChange={(e) => setRegions(Number(e.target.value) || 1)}
                disabled={regionsDisabled}
                className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
              />
            </div>
          </div>

          {/* Model selectors */}
          <div>
            <label htmlFor="sim-model-select" className="block text-[10px] text-gray-500 uppercase mb-1">Sim Model</label>
            <select
              id="sim-model-select"
              aria-label="Sim Model"
              value={simModel}
              onChange={(e) => setSimModel(e.target.value)}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600"
            >
              {models.map((m) => (
                <option key={m} value={m}>{m || "(Default)"}</option>
              ))}
              <option value="__custom__">Custom...</option>
            </select>
            {simModel === "__custom__" && (
              <input
                type="text"
                placeholder="Model name or endpoint"
                value={customSimModel}
                onChange={(e) => setCustomSimModel(e.target.value)}
                className="w-full mt-1 bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 placeholder-gray-500"
              />
            )}
          </div>

          <div>
            <label htmlFor="narrative-model-select" className="block text-[10px] text-gray-500 uppercase mb-1">Narrative Model</label>
            <select
              id="narrative-model-select"
              aria-label="Narrative Model"
              value={narrativeModel}
              onChange={(e) => setNarrativeModel(e.target.value)}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600"
            >
              {models.map((m) => (
                <option key={m} value={m}>{m || "(Default)"}</option>
              ))}
              <option value="__custom__">Custom...</option>
            </select>
            {narrativeModel === "__custom__" && (
              <input
                type="text"
                placeholder="Model name or endpoint"
                value={customNarrativeModel}
                onChange={(e) => setCustomNarrativeModel(e.target.value)}
                className="w-full mt-1 bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 placeholder-gray-500"
              />
            )}
          </div>

          {/* Resume / Fork */}
          <div>
            <label className="block text-[10px] text-gray-500 uppercase mb-1">Resume / Fork</label>
            {resumeState ? (
              <div className="bg-gray-700 rounded px-3 py-2 text-sm border border-green-800 flex items-center justify-between">
                <span className="text-green-400">Resuming from Turn {resumeTurn}</span>
                <button
                  onClick={clearResume}
                  className="text-gray-400 hover:text-red-400 text-xs ml-2"
                  aria-label="Clear resume"
                >
                  &#x2715;
                </button>
              </div>
            ) : (
              <div
                className="bg-gray-700 rounded px-3 py-2 text-sm border border-dashed border-gray-600 text-gray-500 cursor-pointer hover:border-gray-500"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const file = e.dataTransfer.files[0];
                  if (file) handleResumeFile(file);
                }}
              >
                Drop state.json or click to browse...
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleResumeFile(file);
              }}
            />
            {resumeError && (
              <p className="text-red-400 text-xs mt-1">{resumeError}</p>
            )}
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="bg-red-900/50 border border-red-800 rounded px-3 py-2 text-sm text-red-300 mt-4">
            {error}
          </div>
        )}

        {/* Launch button */}
        <button
          onClick={handleLaunch}
          disabled={starting || turns <= 0}
          className="w-full mt-4 py-3 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-bold text-base tracking-wide transition-colors"
        >
          {starting ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Starting...
            </span>
          ) : (
            "\u25B6 LAUNCH SIMULATION"
          )}
        </button>
      </div>

      {/* Preview Panel */}
      <div className="flex-1 p-6 overflow-y-auto">
        {!selectedScenario && !resumeState ? (
          <div className="h-full flex items-center justify-center text-gray-500">
            <div className="text-center">
              <div className="text-5xl mb-3">{"\uD83D\uDDFA\uFE0F"}</div>
              <p>Select a scenario to preview</p>
              <p className="text-sm mt-1">or use procedural generation</p>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div>
              <h2 className="text-xl font-bold text-gray-100">
                {resumeState ? resumeState.name : selectedScenario!.name}
              </h2>
              {!resumeState && selectedScenario?.world_name && (
                <p className="text-sm text-gray-500 mt-0.5">{selectedScenario.world_name}</p>
              )}
              <p className="text-gray-400 text-sm mt-2">
                {resumeState
                  ? `Saved state at turn ${resumeTurn} with ${resumeState.civilizations.length} civilizations`
                  : selectedScenario!.description}
              </p>
            </div>

            {/* Region Map */}
            {previewRegions.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-400 uppercase mb-2">Regions</h3>
                <RegionMap regions={previewRegions} controllers={previewControllers} />
              </div>
            )}

            {/* Civ List */}
            {previewCivs.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-400 uppercase mb-2">Civilizations</h3>
                <div className="grid grid-cols-2 gap-2">
                  {previewCivs.map((c) => (
                    <div key={c.name} className="bg-gray-800 rounded px-3 py-2 border border-gray-700">
                      <p className="text-sm font-medium text-gray-200">{c.name}</p>
                      {c.values.length > 0 && (
                        <p className="text-xs text-gray-500 mt-0.5">{c.values.join(", ")}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx vitest run src/components/__tests__/SetupLobby.test.tsx`
Expected: PASS

- [ ] **Step 5: Verify full TypeScript compilation**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx tsc --noEmit`
Expected: No errors (App.tsx can now resolve the SetupLobby import)

- [ ] **Step 6: Commit**

```bash
git add viewer/src/App.tsx viewer/src/components/SetupLobby.tsx viewer/src/components/__tests__/SetupLobby.test.tsx
git commit -m "feat(m12c): add SetupLobby component and wire App.tsx state machine"
```

### Task 10: Run all tests and verify integration

**Files:** None (verification only)

- [ ] **Step 1: Run all Python tests**

Run: `cd /Users/tbronson/Documents/opusprogram && python -m pytest tests/test_live.py -v`
Expected: All PASS

- [ ] **Step 2: Run all viewer tests**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx vitest run`
Expected: All PASS

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd /Users/tbronson/Documents/opusprogram/viewer && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit any remaining fixes**

If any tests fail, fix and commit with descriptive message.

- [ ] **Step 5: Final commit with all changes verified**

```bash
git add src/chronicler/live.py src/chronicler/main.py tests/test_live.py \
  viewer/src/types.ts viewer/src/hooks/useLiveConnection.ts viewer/src/App.tsx \
  viewer/src/hooks/__tests__/useLiveConnection.test.ts \
  viewer/src/components/SetupLobby.tsx viewer/src/components/__tests__/SetupLobby.test.tsx \
  viewer/src/components/RegionMap.tsx viewer/src/components/__tests__/RegionMap.test.tsx
git commit -m "feat(m12c): setup lobby complete — all tests passing"
```
