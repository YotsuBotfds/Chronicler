# Narrative Context Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the 7 bridge-owned narrative inputs through to narration callers so in-process narration gets full agent context and replay degrades gracefully.

**Architecture:** Explicit kwargs at callers — no engine-internal bridge access. One new kwarg (`dynasty_registry`) on two signatures. Gini fallback from snapshot in `build_agent_context_for_moment()`. Three callers: post-loop (full bridge context), `_run_narrate()` (bundle-derived), `live.py narrate_range` (bundle-derived + stale-GP caveat).

**Tech Stack:** Python only — `narrative.py`, `main.py`, `live.py`, plus tests.

**Spec:** `docs/superpowers/specs/2026-04-03-narrative-context-wiring-design.md`

---

### Task 1: Add `dynasty_registry` to narrative signatures and thread through

**Files:**
- Modify: `src/chronicler/narrative.py:911-944` (`narrate_batch`)
- Modify: `src/chronicler/narrative.py:958-969` (`_prepare_narration_prompts`)
- Modify: `src/chronicler/narrative.py:1075-1091` (call to `build_agent_context_for_moment`)
- Test: `tests/test_narrative.py`

- [ ] **Step 1: Write failing test — dynasty_registry threads through to agent context**

In `tests/test_narrative.py`, add a test near the existing Gini plumbing test (~line 545). This test verifies that when `dynasty_registry` is passed to `_prepare_narration_prompts()`, it reaches `build_agent_context_for_moment()` and dynasty lineage appears in the output.

```python
def test_dynasty_registry_threads_through_prepare_prompts(sample_world):
    """dynasty_registry kwarg propagates from _prepare_narration_prompts to agent context."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import (
        NarrativeMoment, GreatPerson, TurnSnapshot, CivStats,
    )

    # Create a great person with dynasty info
    gp = GreatPerson(
        name="Kael the Bold",
        role="general",
        civilization="Ironforge",
        source="agent",
        agent_id=10,
        active=True,
        born_turn=1,
        dynasty_id=1,
    )

    moment = NarrativeMoment(
        turn_range=(5, 5),
        anchor_turn=5,
        events=[MagicMock(
            turn=5, description="Battle", source="agent",
            actors=["Kael the Bold"], severity=5, event_type="war",
            causal_parent_id=None, causal_children_ids=[],
        )],
        title="A Battle",
    )

    snap = TurnSnapshot(
        turn=5,
        civ_stats={"Ironforge": CivStats(population=100, regions=1)},
    )
    history = [snap]

    # Build a mock dynasty registry that returns a dynasty for agent 10
    mock_registry = MagicMock()
    mock_dynasty = MagicMock()
    mock_dynasty.founder_name = "House of Kael"
    mock_dynasty.members = [10, 11, 12]
    mock_dynasty.split_detected = False
    mock_registry.get_dynasty_for.return_value = mock_dynasty

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=MagicMock(model="test"),
    )
    engine._world = sample_world

    prepared = engine._prepare_narration_prompts(
        [moment],
        history,
        great_persons=[gp],
        dynasty_registry=mock_registry,
    )

    assert prepared[0]["agent_ctx"] is not None
    # Dynasty context should reach the character entry
    char = prepared[0]["agent_ctx"].named_characters[0]
    assert char["dynasty"] == "House of Kael"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_narrative.py::test_dynasty_registry_threads_through_prepare_prompts -v`
Expected: FAIL — `_prepare_narration_prompts()` does not accept `dynasty_registry` kwarg.

- [ ] **Step 3: Add `dynasty_registry` kwarg to `narrate_batch()` and `_prepare_narration_prompts()`**

In `src/chronicler/narrative.py`, modify `narrate_batch()` at line 911 — add `dynasty_registry=None` parameter after `displacement_by_region`:

```python
    def narrate_batch(
        self,
        moments: list[NarrativeMoment],
        history: Sequence[TurnSnapshot],
        on_progress: Callable[[int, int, float | None], None] | None = None,
        # M40: Optional agent context data
        great_persons: list | None = None,
        social_edges: list[tuple] | None = None,
        dissolved_edges_by_turn: dict[int, list[tuple]] | None = None,
        agent_name_map: dict[int, str] | None = None,
        # M41: per-civ Gini coefficients for wealth inequality narration
        gini_by_civ: dict[int, float] | None = None,
        # M43b: Economy result for trade dependency and shock narration
        economy_result=None,
        # M52: World state for artifact context in prompts
        world=None,
        # Displacement fractions by region index (from agent bridge)
        displacement_by_region: dict[int, float] | None = None,
        # M39: Dynasty registry for lineage narration
        dynasty_registry=None,
    ) -> list[ChronicleEntry]:
```

Thread it to the `_prepare_narration_prompts()` call at line 941:

```python
        prepared = self._prepare_narration_prompts(
            moments, history, great_persons, social_edges,
            dissolved_edges_by_turn, agent_name_map, gini_by_civ,
            economy_result, displacement_by_region=displacement_by_region,
            dynasty_registry=dynasty_registry,
        )
```

Modify `_prepare_narration_prompts()` at line 958 — add `dynasty_registry=None` parameter:

```python
    def _prepare_narration_prompts(
        self,
        moments: list[NarrativeMoment],
        history: Sequence[TurnSnapshot],
        great_persons: list | None = None,
        social_edges: list[tuple] | None = None,
        dissolved_edges_by_turn: dict[int, list[tuple]] | None = None,
        agent_name_map: dict[int, str] | None = None,
        gini_by_civ: dict[int, float] | None = None,
        economy_result=None,
        displacement_by_region: dict[int, float] | None = None,
        dynasty_registry=None,
    ) -> list[dict]:
```

Thread it to the `build_agent_context_for_moment()` call at line 1075 — add `dynasty_registry=dynasty_registry`:

```python
                agent_ctx = build_agent_context_for_moment(
                    moment, great_persons,
                    displacement_by_region=displacement_by_region or {},
                    dynasty_registry=dynasty_registry,
                    gp_by_agent_id=gp_by_agent_id,
                    social_edges=social_edges,
                    dissolved_edges=moment_dissolved if moment_dissolved else None,
                    agent_name_map=agent_name_map,
                    hostage_data=hostage_data,
                    civ_idx=civ_idx,
                    gini_by_civ=gini_by_civ,
                    economy_result=economy_result,
                    civ_names=civ_names,
                    world_turn=moment.anchor_turn,
                    history=history,
                    current_snapshot=snap,
                    world=world_obj,
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_narrative.py::test_dynasty_registry_threads_through_prepare_prompts -v`
Expected: PASS

- [ ] **Step 5: Write test — dynasty_registry=None produces no dynasty text and no error**

```python
def test_dynasty_registry_none_degrades_gracefully(sample_world):
    """When dynasty_registry is None, no dynasty text appears and no error."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import (
        NarrativeMoment, GreatPerson, TurnSnapshot, CivStats,
    )

    gp = GreatPerson(
        name="Kael the Bold",
        role="general",
        civilization="Ironforge",
        source="agent",
        agent_id=10,
        active=True,
        born_turn=1,
    )

    moment = NarrativeMoment(
        turn_range=(5, 5),
        anchor_turn=5,
        events=[MagicMock(
            turn=5, description="Battle", source="agent",
            actors=["Kael the Bold"], severity=5, event_type="war",
            causal_parent_id=None, causal_children_ids=[],
        )],
        title="A Battle",
    )

    snap = TurnSnapshot(
        turn=5,
        civ_stats={"Ironforge": CivStats(population=100, regions=1)},
    )

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=MagicMock(model="test"),
    )
    engine._world = sample_world

    prepared = engine._prepare_narration_prompts(
        [moment],
        [snap],
        great_persons=[gp],
        dynasty_registry=None,
    )

    assert prepared[0]["agent_ctx"] is not None
    char = prepared[0]["agent_ctx"].named_characters[0]
    assert "dynasty" not in char
```

- [ ] **Step 6: Run both dynasty tests**

Run: `pytest tests/test_narrative.py -k "dynasty_registry" -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/narrative.py tests/test_narrative.py
git commit -m "feat: add dynasty_registry kwarg to narrate_batch and _prepare_narration_prompts"
```

---

### Task 2: Gini fallback from snapshot in `build_agent_context_for_moment()`

**Files:**
- Modify: `src/chronicler/narrative.py:468-469` (Gini resolution line)
- Test: `tests/test_narrative.py`

- [ ] **Step 1: Write failing test — Gini fallback from snapshot when gini_by_civ is None**

Add near the existing Gini test at `tests/test_narrative.py:545`:

```python
def test_gini_fallback_from_snapshot_when_gini_by_civ_none(sample_world):
    """When gini_by_civ is None, Gini falls back to snapshot civ_stats."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import (
        NarrativeMoment, GreatPerson, TurnSnapshot, CivStats,
    )

    gp = GreatPerson(
        name="Kael the Bold",
        role="general",
        civilization="Ironforge",
        source="agent",
        agent_id=10,
        active=True,
        born_turn=1,
    )

    moment = NarrativeMoment(
        turn_range=(5, 5),
        anchor_turn=5,
        events=[MagicMock(
            turn=5, description="Battle", source="agent",
            actors=["Kael the Bold"], severity=5, event_type="war",
            causal_parent_id=None, causal_children_ids=[],
        )],
        title="A Battle",
    )

    snap = TurnSnapshot(
        turn=5,
        civ_stats={"Ironforge": CivStats(population=100, regions=1, gini=0.42)},
    )

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=MagicMock(model="test"),
    )
    engine._world = sample_world

    prepared = engine._prepare_narration_prompts(
        [moment],
        [snap],
        great_persons=[gp],
        gini_by_civ=None,
    )

    assert prepared[0]["agent_ctx"] is not None
    assert prepared[0]["agent_ctx"].gini_coefficient == pytest.approx(0.42)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_narrative.py::test_gini_fallback_from_snapshot_when_gini_by_civ_none -v`
Expected: FAIL — `gini_coefficient` will be `0.0` (the default) because the fallback doesn't exist yet.

- [ ] **Step 3: Implement Gini fallback in `build_agent_context_for_moment()`**

In `src/chronicler/narrative.py`, the Gini line at 468-469 runs BEFORE `focal_civ` is resolved at 472-482. The fallback needs `focal_civ` (a civ name) to look up snapshot Gini. Fix: move the Gini resolution block to AFTER the `focal_civ` block.

Delete the old Gini line at 468-469:
```python
    # M41: Gini coefficient for wealth inequality context
    gini = (gini_by_civ or {}).get(civ_idx, 0.0) if civ_idx is not None else 0.0
```

Insert the new Gini block immediately after the `focal_civ` resolution block (after line 482, before the urbanization delta block at line 484):

```python
    # M41: Gini coefficient for wealth inequality context
    # Step 1: try live bridge data (gini_by_civ keyed by civ index)
    gini = (gini_by_civ or {}).get(civ_idx, None) if civ_idx is not None else None
    # Step 2: fallback to snapshot civ_stats (keyed by civ name)
    if gini is None and current_snapshot is not None and focal_civ is not None:
        snap_stats = current_snapshot.civ_stats.get(focal_civ)
        if snap_stats is not None and snap_stats.gini is not None:
            gini = snap_stats.gini
    # Step 3: default — no signal
    if gini is None:
        gini = 0.0
```

The `gini` variable is consumed later in the `AgentContext` constructor at ~line 518, which is unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_narrative.py::test_gini_fallback_from_snapshot_when_gini_by_civ_none -v`
Expected: PASS

- [ ] **Step 5: Write test — no snapshot and no gini_by_civ gives default 0.0**

```python
def test_gini_no_source_keeps_default():
    """When both gini_by_civ and snapshot gini are absent, gini stays at 0.0."""
    from unittest.mock import MagicMock
    from chronicler.narrative import build_agent_context_for_moment
    from chronicler.models import NarrativeMoment, GreatPerson, TurnSnapshot, CivStats

    gp = GreatPerson(
        name="Kael the Bold",
        role="general",
        civilization="Ironforge",
        source="agent",
        agent_id=10,
        active=True,
        born_turn=1,
    )

    moment = NarrativeMoment(
        turn_range=(5, 5),
        anchor_turn=5,
        events=[MagicMock(
            turn=5, description="Battle", source="agent",
            actors=["Kael the Bold"], severity=5, event_type="war",
            causal_parent_id=None, causal_children_ids=[],
        )],
        title="A Battle",
    )

    # Snapshot with default gini (0.0)
    snap = TurnSnapshot(
        turn=5,
        civ_stats={"Ironforge": CivStats(population=100, regions=1)},
    )

    ctx = build_agent_context_for_moment(
        moment,
        [gp],
        displacement_by_region={},
        gini_by_civ=None,
        civ_idx=0,
        current_snapshot=snap,
    )

    assert ctx is not None
    assert ctx.gini_coefficient == 0.0
```

- [ ] **Step 6: Run all Gini tests**

Run: `pytest tests/test_narrative.py -k "gini" -v`
Expected: All pass (existing + 2 new)

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/narrative.py tests/test_narrative.py
git commit -m "feat: Gini fallback from snapshot when gini_by_civ is None"
```

---

### Task 3: Wire post-loop narration caller in `main.py`

**Files:**
- Modify: `src/chronicler/main.py:627-631` (post-loop `narrate_batch()` call)
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing test — post-loop narration passes bridge context**

In `tests/test_main.py`, add a test that verifies the post-loop narration caller passes all 7 bridge-owned inputs. This test monkeypatches `NarrativeEngine.narrate_batch` and checks the kwargs:

```python
def test_post_loop_narration_passes_bridge_context(tmp_path, monkeypatch):
    """Post-loop API narration threads all bridge-owned inputs to narrate_batch."""
    import argparse
    from unittest.mock import MagicMock, patch
    from chronicler.main import execute_run

    captured_kwargs = {}

    def spy_narrate_batch(self, moments, history, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(
        "chronicler.narrative.NarrativeEngine.narrate_batch",
        spy_narrate_batch,
    )

    args = argparse.Namespace(
        seed=42, turns=5, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None,
        simulate_only=False, agents="hybrid",
        budget=50, narrator="local",
        pause_every=None,
        narrative_model=None,
    )

    # Mock the LLM clients so we don't need a real server
    mock_client = MagicMock()
    mock_client.model = "test"
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Narrated text."))]
    )

    with patch("chronicler.main.create_clients", return_value=(mock_client, mock_client)):
        execute_run(args)

    # All 7 bridge-owned inputs should be present and non-None
    assert "social_edges" in captured_kwargs
    assert "dissolved_edges_by_turn" in captured_kwargs
    assert "agent_name_map" in captured_kwargs
    assert "gini_by_civ" in captured_kwargs
    assert "economy_result" in captured_kwargs
    assert "displacement_by_region" in captured_kwargs
    assert "dynasty_registry" in captured_kwargs
```

Note: This test may need adjustment based on how `execute_run` is structured and what mocks are needed. The implementing agent should verify the exact mocking requirements by reading the test patterns in `tests/test_main.py:913` and adapting. The key assertion is that all 7 kwargs arrive non-None.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_post_loop_narration_passes_bridge_context -v`
Expected: FAIL — the current call at `main.py:627` does not pass these kwargs.

- [ ] **Step 3: Wire bridge context into post-loop narration call**

In `src/chronicler/main.py`, modify the `narrate_batch()` call at ~line 627. The `agent_bridge` variable is still alive at this point (it's closed at line 642-644).

Old:
```python
        chronicle_entries = engine.narrate_batch(
            moments, history, on_progress=progress_cb,
            great_persons=all_great_persons,
            world=world,
        )
```

New:
```python
        chronicle_entries = engine.narrate_batch(
            moments, history, on_progress=progress_cb,
            great_persons=all_great_persons,
            world=world,
            social_edges=agent_bridge.read_social_edges() if agent_bridge is not None else None,
            dissolved_edges_by_turn=world.dissolved_edges_by_turn if hasattr(world, "dissolved_edges_by_turn") else None,
            agent_name_map=agent_bridge.named_agents if agent_bridge is not None else None,
            gini_by_civ=agent_bridge._gini_by_civ if agent_bridge is not None else None,
            economy_result=agent_bridge._economy_result if agent_bridge is not None else None,
            displacement_by_region=agent_bridge.displacement_by_region if agent_bridge is not None else None,
            dynasty_registry=agent_bridge.dynasty_registry if agent_bridge is not None else None,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py::test_post_loop_narration_passes_bridge_context -v`
Expected: PASS

- [ ] **Step 5: Run existing main tests to check for regressions**

Run: `pytest tests/test_main.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat: wire bridge-owned narrative context into post-loop narration"
```

---

### Task 4: Wire replay `_run_narrate()` with bundle-derived context

**Files:**
- Modify: `src/chronicler/main.py:1005-1009` (`_run_narrate` narrate_batch call)
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing test — replay passes agent_name_map and great_persons, bridge-only inputs are None**

```python
def test_run_narrate_passes_bundle_derived_context(tmp_path, monkeypatch):
    """_run_narrate passes agent_name_map from great_persons, None for bridge-only inputs."""
    import argparse
    from unittest.mock import MagicMock, patch
    from chronicler.main import execute_run, _run_narrate

    captured_kwargs = {}

    def spy_narrate_batch(self, moments, history, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    # First, generate a simulate-only bundle with agents
    sim_args = argparse.Namespace(
        seed=42, turns=10, civs=2, regions=4,
        output=str(tmp_path / "chronicle.md"),
        state=str(tmp_path / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None,
        simulate_only=True, agents="hybrid",
        budget=50, narrator="local",
        pause_every=None,
    )
    execute_run(sim_args)

    bundle_path = tmp_path / "chronicle_bundle.json"
    assert bundle_path.exists()

    monkeypatch.setattr(
        "chronicler.narrative.NarrativeEngine.narrate_batch",
        spy_narrate_batch,
    )

    narrate_args = argparse.Namespace(
        narrate=bundle_path,
        output=str(tmp_path / "narrated.md"),
        budget=50,
        narrator="local",
        narrative_model=None,
    )

    mock_client = MagicMock()
    mock_client.model = "test"
    with patch("chronicler.main.create_clients", return_value=(mock_client, mock_client)):
        _run_narrate(narrate_args)

    # great_persons should be the full list (not filtered)
    assert captured_kwargs.get("great_persons") is not None

    # agent_name_map should be derived from great_persons
    gps = captured_kwargs["great_persons"]
    expected_map = {gp.agent_id: gp.name for gp in gps if gp.agent_id is not None}
    assert captured_kwargs.get("agent_name_map") == expected_map

    # Bridge-only inputs should be explicitly None
    assert captured_kwargs.get("social_edges") is None
    assert captured_kwargs.get("dissolved_edges_by_turn") is None
    assert captured_kwargs.get("displacement_by_region") is None
    assert captured_kwargs.get("dynasty_registry") is None
    assert captured_kwargs.get("economy_result") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::test_run_narrate_passes_bundle_derived_context -v`
Expected: FAIL — current call at `main.py:1005` does not pass `agent_name_map`.

- [ ] **Step 3: Wire bundle-derived context into `_run_narrate()`**

In `src/chronicler/main.py`, modify the `narrate_batch()` call at ~line 1005.

Old:
```python
    chronicle_entries = engine.narrate_batch(
        moments, history, on_progress=progress_cb,
        great_persons=all_great_persons,
        world=world,
    )
```

New:
```python
    # Build agent_name_map from bundled great_persons (agent_id filter on map only)
    agent_name_map = (
        {gp.agent_id: gp.name for gp in all_great_persons if gp.agent_id is not None}
        if all_great_persons else None
    )

    chronicle_entries = engine.narrate_batch(
        moments, history, on_progress=progress_cb,
        great_persons=all_great_persons,
        world=world,
        agent_name_map=agent_name_map,
        # Bridge-only inputs — not available on replay
        social_edges=None,
        dissolved_edges_by_turn=None,
        displacement_by_region=None,
        dynasty_registry=None,
        economy_result=None,
        gini_by_civ=None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_main.py::test_run_narrate_passes_bundle_derived_context -v`
Expected: PASS

- [ ] **Step 5: Run existing _run_narrate tests**

Run: `pytest tests/test_main.py -k "run_narrate" -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat: wire bundle-derived narrative context into _run_narrate replay"
```

---

### Task 5: Wire live `narrate_range` with bundle-derived context

**Files:**
- Modify: `src/chronicler/live.py:598-628` (narrate_range handler)
- Test: `tests/test_live_integration.py`

- [ ] **Step 1: Write failing test — live narrate_range passes great_persons and agent_name_map**

In `tests/test_live_integration.py`, add a test that verifies the narrate_range caller passes `great_persons` and `agent_name_map`. This test monkeypatches `NarrativeEngine.narrate_batch` and checks the kwargs:

```python
@pytest.mark.asyncio
async def test_narrate_range_passes_great_persons_and_agent_name_map(running_live_server, monkeypatch):
    """Live narrate_range threads great_persons and agent_name_map from _init_data."""
    captured_kwargs = {}

    original_narrate = None

    def spy_narrate_batch(self, moments, history, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(
        "chronicler.narrative.NarrativeEngine.narrate_batch",
        spy_narrate_batch,
    )

    async with ws_client.connect(f"ws://localhost:{running_live_server._actual_port}") as ws:
        init_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        init_msg = json.loads(init_raw)
        assert init_msg["state"] == "running"

        # Wait for at least one turn
        while True:
            msg_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            msg = json.loads(msg_raw)
            if msg.get("type") == "turn" and msg.get("turn", 0) >= 2:
                break

        # Pause
        await ws.send(json.dumps({"type": "pause"}))
        pause_msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))

        # Send narrate_range
        await ws.send(json.dumps({
            "type": "narrate_range",
            "start_turn": 1,
            "end_turn": 2,
        }))

        # Read response (could be narration_complete or error)
        resp_raw = await asyncio.wait_for(ws.recv(), timeout=15.0)

    # great_persons kwarg should be present (may be empty list if no GPs promoted yet)
    assert "great_persons" in captured_kwargs
    # agent_name_map should be present
    assert "agent_name_map" in captured_kwargs
    # Bridge-only inputs should be None
    assert captured_kwargs.get("social_edges") is None
    assert captured_kwargs.get("dynasty_registry") is None
```

Note: The implementing agent should adapt this test to the existing patterns in `tests/test_live_integration.py:529`. The `running_live_server` fixture and `ws_client` imports need to match the existing test infrastructure.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_live_integration.py::test_narrate_range_passes_great_persons_and_agent_name_map -v`
Expected: FAIL — current call at `live.py:628` passes no kwargs.

- [ ] **Step 3: Wire great_persons, agent_name_map, and explicit None kwargs into narrate_range**

In `src/chronicler/live.py`, modify the narrate_range handler at ~line 598-628. After the existing `named_chars` collection (line 606-610), add GP reconstruction and wire into the narrate_batch call:

Old (line 628):
```python
                            entries = engine.narrate_batch(moments, all_history)
```

New — after the `named_chars` block (~line 610), add great_persons reconstruction:

```python
                        # Reconstruct great_persons from _init_data world state
                        from chronicler.models import GreatPerson as _GP
                        all_great_persons = []
                        for civ_data in self._init_data.get("world_state", {}).get("civilizations", []):
                            for gp_data in civ_data.get("great_persons", []):
                                all_great_persons.append(_GP(**gp_data))
                        for gp_data in self._init_data.get("world_state", {}).get("retired_persons", []):
                            all_great_persons.append(_GP(**gp_data))

                        agent_name_map = (
                            {gp.agent_id: gp.name for gp in all_great_persons if gp.agent_id is not None}
                            if all_great_persons else None
                        )
```

Then update the narrate_batch call:

```python
                            entries = engine.narrate_batch(
                                moments, all_history,
                                great_persons=all_great_persons if all_great_persons else None,
                                agent_name_map=agent_name_map,
                                # Bridge-only inputs — not available in live replay
                                social_edges=None,
                                dissolved_edges_by_turn=None,
                                displacement_by_region=None,
                                dynasty_registry=None,
                                economy_result=None,
                                gini_by_civ=None,
                            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_live_integration.py::test_narrate_range_passes_great_persons_and_agent_name_map -v`
Expected: PASS

- [ ] **Step 5: Run existing live integration tests**

Run: `pytest tests/test_live_integration.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/chronicler/live.py tests/test_live_integration.py
git commit -m "feat: wire great_persons and agent_name_map into live narrate_range"
```

---

### Task 6: Final regression and push

**Files:** None — verification only.

- [ ] **Step 1: Run full narrative test suite**

Run: `pytest tests/test_narrative.py -v`
Expected: All pass

- [ ] **Step 2: Run full main test suite**

Run: `pytest tests/test_main.py -v`
Expected: All pass

- [ ] **Step 3: Run full live integration test suite**

Run: `pytest tests/test_live_integration.py -v`
Expected: All pass

- [ ] **Step 4: Run complete test suite**

Run: `pytest tests/ -v`
Expected: All pass, no regressions

- [ ] **Step 5: Push**

```bash
git push
```
