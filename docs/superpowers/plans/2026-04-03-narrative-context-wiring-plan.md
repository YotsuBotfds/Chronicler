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

In `tests/test_narrative.py`, add a test near the existing Gini plumbing test (~line 545). Mirror the model shapes from the existing `test_prepare_narration_prompts_threads_focal_civ_gini` test at line 494. Use `sample_world` fixture, real `Event` and `CivSnapshot` constructors, full `NarrativeMoment` with all required fields.

```python
def test_dynasty_registry_threads_through_prepare_prompts(sample_world):
    """dynasty_registry kwarg propagates from _prepare_narration_prompts to agent context."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import (
        CivSnapshot, Event, GreatPerson, NarrativeMoment, NarrativeRole, TurnSnapshot,
    )

    civ_name = sample_world.civilizations[0].name
    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization=civ_name,
        origin_civilization=civ_name,
        born_turn=5,
        source="agent",
        agent_id=42,
        dynasty_id=1,
    )

    moment = NarrativeMoment(
        anchor_turn=10,
        turn_range=(10, 10),
        events=[Event(
            turn=10,
            event_type="campaign",
            actors=[civ_name],
            description="A campaign unfolds",
            importance=7,
            source="agent",
        )],
        named_events=[],
        score=8.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )

    history = [TurnSnapshot(
        turn=10,
        civ_stats={
            civ_name: CivSnapshot(
                population=50, military=30, economy=40, culture=35,
                stability=55, treasury=20, asabiya=0.5, tech_era="iron",
                trait="bold", regions=list(sample_world.civilizations[0].regions),
                leader_name=sample_world.civilizations[0].leader.name, alive=True,
            )
        },
        region_control={},
        relationships={},
    )]

    # Build a mock dynasty registry that returns a dynasty for agent 42
    mock_registry = MagicMock()
    mock_dynasty = MagicMock()
    mock_dynasty.founder_name = "House of Kiran"
    mock_dynasty.members = [42, 43, 44]
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
    assert char["dynasty"] == "House of Kiran"
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
        CivSnapshot, Event, GreatPerson, NarrativeMoment, NarrativeRole, TurnSnapshot,
    )

    civ_name = sample_world.civilizations[0].name
    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization=civ_name,
        origin_civilization=civ_name,
        born_turn=5,
        source="agent",
        agent_id=42,
    )

    moment = NarrativeMoment(
        anchor_turn=10,
        turn_range=(10, 10),
        events=[Event(
            turn=10,
            event_type="campaign",
            actors=[civ_name],
            description="A campaign unfolds",
            importance=7,
            source="agent",
        )],
        named_events=[],
        score=8.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )

    history = [TurnSnapshot(
        turn=10,
        civ_stats={
            civ_name: CivSnapshot(
                population=50, military=30, economy=40, culture=35,
                stability=55, treasury=20, asabiya=0.5, tech_era="iron",
                trait="bold", regions=list(sample_world.civilizations[0].regions),
                leader_name=sample_world.civilizations[0].leader.name, alive=True,
            )
        },
        region_control={},
        relationships={},
    )]

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=MagicMock(model="test"),
    )
    engine._world = sample_world

    prepared = engine._prepare_narration_prompts(
        [moment],
        history,
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
- Modify: `src/chronicler/narrative.py:468-469` (Gini resolution line — move after `focal_civ` block)
- Test: `tests/test_narrative.py`

- [ ] **Step 1: Write failing test — Gini fallback from snapshot when gini_by_civ is None**

Add near the existing Gini test at `tests/test_narrative.py:545`. Mirror the existing test shape.

```python
def test_gini_fallback_from_snapshot_when_gini_by_civ_none(sample_world):
    """When gini_by_civ is None, Gini falls back to snapshot civ_stats."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import (
        CivSnapshot, Event, GreatPerson, NarrativeMoment, NarrativeRole, TurnSnapshot,
    )

    civ_name = sample_world.civilizations[0].name
    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization=civ_name,
        origin_civilization=civ_name,
        born_turn=5,
        source="agent",
        agent_id=42,
    )

    moment = NarrativeMoment(
        anchor_turn=10,
        turn_range=(10, 10),
        events=[Event(
            turn=10,
            event_type="campaign",
            actors=[civ_name],
            description="A campaign unfolds",
            importance=7,
            source="agent",
        )],
        named_events=[],
        score=8.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )

    history = [TurnSnapshot(
        turn=10,
        civ_stats={
            civ_name: CivSnapshot(
                population=50, military=30, economy=40, culture=35,
                stability=55, treasury=20, asabiya=0.5, tech_era="iron",
                trait="bold", regions=list(sample_world.civilizations[0].regions),
                leader_name=sample_world.civilizations[0].leader.name, alive=True,
                gini=0.42,
            )
        },
        region_control={},
        relationships={},
    )]

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=MagicMock(model="test"),
    )
    engine._world = sample_world

    prepared = engine._prepare_narration_prompts(
        [moment],
        history,
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

- [ ] **Step 5: Write test — no snapshot Gini and no gini_by_civ gives default 0.0**

```python
def test_gini_no_source_keeps_default(sample_world):
    """When both gini_by_civ and snapshot gini are absent, gini stays at 0.0."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import (
        CivSnapshot, Event, GreatPerson, NarrativeMoment, NarrativeRole, TurnSnapshot,
    )

    civ_name = sample_world.civilizations[0].name
    gp = GreatPerson(
        name="Kiran",
        role="general",
        trait="bold",
        civilization=civ_name,
        origin_civilization=civ_name,
        born_turn=5,
        source="agent",
        agent_id=42,
    )

    moment = NarrativeMoment(
        anchor_turn=10,
        turn_range=(10, 10),
        events=[Event(
            turn=10,
            event_type="campaign",
            actors=[civ_name],
            description="A campaign unfolds",
            importance=7,
            source="agent",
        )],
        named_events=[],
        score=8.0,
        causal_links=[],
        narrative_role=NarrativeRole.CLIMAX,
        bonus_applied=0.0,
    )

    # CivSnapshot with default gini (0.0) — no explicit gini= kwarg
    history = [TurnSnapshot(
        turn=10,
        civ_stats={
            civ_name: CivSnapshot(
                population=50, military=30, economy=40, culture=35,
                stability=55, treasury=20, asabiya=0.5, tech_era="iron",
                trait="bold", regions=list(sample_world.civilizations[0].regions),
                leader_name=sample_world.civilizations[0].leader.name, alive=True,
            )
        },
        region_control={},
        relationships={},
    )]

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=MagicMock(model="test"),
    )
    engine._world = sample_world

    prepared = engine._prepare_narration_prompts(
        [moment],
        history,
        great_persons=[gp],
        gini_by_civ=None,
    )

    assert prepared[0]["agent_ctx"] is not None
    # Default CivSnapshot.gini is 0.0, which the fallback reads but is equivalent to no-signal
    assert prepared[0]["agent_ctx"].gini_coefficient == 0.0
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

In `tests/test_main.py`, add a test inside or near `TestApiNarration`. The post-loop narration path only fires when `_api_mode` is true (line 150-151: `_narrator_mode != "local"`), so the test must use `narrator="api"` and pass a mocked API client via `execute_run(args, narrative_client=...)`. Follow the pattern at `tests/test_main.py:859` (`test_api_mode_produces_curated_entries_with_metadata`).

```python
def test_post_loop_narration_passes_bridge_context(self, tmp_path):
    """Post-loop API narration threads all bridge-owned inputs to narrate_batch."""
    from unittest.mock import MagicMock, patch
    from chronicler.llm import AnthropicClient

    captured_kwargs = {}
    original_narrate = None

    def spy_narrate_batch(self_engine, moments, history, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    mock_sdk = MagicMock()
    api_client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")
    def fake_batch_complete(requests, poll_interval=10.0):
        api_client.total_input_tokens += 500
        api_client.total_output_tokens += 200
        api_client.call_count += len(requests)
        return [
            "The great empire rose from humble beginnings..."
            for _ in requests
        ]
    api_client.batch_complete = MagicMock(side_effect=fake_batch_complete)

    args = self._make_args(str(tmp_path))
    # _make_args already sets narrator="api" and agents="off"
    # Override agents to "hybrid" so a bridge exists
    args.agents = "hybrid"

    with patch.object(
        NarrativeEngine, "narrate_batch", spy_narrate_batch,
    ):
        execute_run(
            args,
            sim_client=MagicMock(model="test", complete=MagicMock(return_value="DEVELOP")),
            narrative_client=api_client,
        )

    # All 7 bridge-owned inputs should be present and non-None
    assert "social_edges" in captured_kwargs
    assert "dissolved_edges_by_turn" in captured_kwargs
    assert "agent_name_map" in captured_kwargs
    assert "gini_by_civ" in captured_kwargs
    assert "economy_result" in captured_kwargs
    assert "displacement_by_region" in captured_kwargs
    assert "dynasty_registry" in captured_kwargs
```

Note: This test lives inside `class TestApiNarration` (which starts at ~line 833 and has the `_make_args` helper at line 839). The implementing agent should add it as a method of that class. If the `_make_args` helper doesn't include all needed fields for hybrid mode, the agent should adapt accordingly.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::TestApiNarration::test_post_loop_narration_passes_bridge_context -v`
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

Run: `pytest tests/test_main.py::TestApiNarration::test_post_loop_narration_passes_bridge_context -v`
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

Follow the existing `test_run_narrate_api_mode_writes_metadata` pattern at `tests/test_main.py:913`. Key details: argparse namespace must include `local_url`, `sim_model`, `narrate_output` (not `output`). Generate a simulate-only bundle first, then re-narrate with a spy.

```python
def test_run_narrate_passes_bundle_derived_context(self, tmp_path):
    """_run_narrate passes agent_name_map from great_persons, None for bridge-only inputs."""
    import json
    from unittest.mock import MagicMock, patch
    from chronicler.main import execute_run, _run_narrate
    from chronicler.llm import AnthropicClient

    mock_sdk = MagicMock()

    # First, generate a simulate-only bundle with agents
    sim_args = argparse.Namespace(
        seed=42, turns=20, civs=3, regions=6,
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

    # Spy on narrate_batch
    captured_kwargs = {}

    def spy_narrate_batch(self_engine, moments, history, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    narrate_args = argparse.Namespace(
        narrate=bundle_path,
        narrator="api",
        local_url="http://localhost:1234/v1",
        sim_model=None,
        narrative_model=None,
        budget=10,
        narrate_output=tmp_path / "narrated.json",
    )

    api_client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")
    def fake_batch_complete(requests, poll_interval=10.0):
        api_client.total_input_tokens += 300
        api_client.total_output_tokens += 150
        api_client.call_count += len(requests)
        return ["Narrated text." for _ in requests]
    api_client.batch_complete = MagicMock(side_effect=fake_batch_complete)

    from chronicler.narrative import NarrativeEngine
    with patch.object(NarrativeEngine, "narrate_batch", spy_narrate_batch):
        with patch("chronicler.main.create_clients",
                   return_value=(MagicMock(model="test"), api_client)):
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

Note: This test lives inside `class TestApiNarration`. The implementing agent should add it as a method of that class.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py::TestApiNarration::test_run_narrate_passes_bundle_derived_context -v`
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

Run: `pytest tests/test_main.py::TestApiNarration::test_run_narrate_passes_bundle_derived_context -v`
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

In `tests/test_live_integration.py`, add a test using the `running_live_server` fixture. This fixture provides skeletal `_init_data` with empty civilizations (line 32-68). The test injects GP data and events into `_init_data` before connecting, then sends `narrate_range` (which is accepted regardless of pause state — it's handled at line 582-634, before the pause-only command check at line 636).

```python
@pytest.mark.asyncio
async def test_narrate_range_passes_great_persons_and_agent_name_map(running_live_server, monkeypatch):
    """Live narrate_range threads great_persons and agent_name_map from _init_data."""
    from chronicler.narrative import NarrativeEngine

    captured_kwargs = {}

    def spy_narrate_batch(self_engine, moments, history, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(NarrativeEngine, "narrate_batch", spy_narrate_batch)

    # Inject GP data and events into _init_data so curate() returns moments
    running_live_server._init_data["world_state"]["civilizations"] = [{
        "name": "TestCiv",
        "regions": ["Region0"],
        "leader": {"name": "TestLeader", "personality": "bold"},
        "great_persons": [
            {
                "name": "Kiran",
                "role": "general",
                "trait": "bold",
                "civilization": "TestCiv",
                "origin_civilization": "TestCiv",
                "born_turn": 1,
                "source": "agent",
                "agent_id": 42,
            }
        ],
        "population": 100,
        "military": 50,
        "economy": 40,
        "culture": 30,
        "stability": 60,
        "treasury": 20,
        "asabiya": 0.5,
        "tech_era": "iron",
        "trait": "bold",
        "alive": True,
    }]
    running_live_server._init_data["world_state"]["retired_persons"] = []
    running_live_server._init_data["events_timeline"] = [
        {
            "turn": 1,
            "event_type": "campaign",
            "actors": ["TestCiv"],
            "description": "A great campaign",
            "importance": 8,
            "source": "agent",
        }
    ]

    async with ws_client.connect(f"ws://localhost:{running_live_server._actual_port}") as ws:
        # Drain the init message
        init_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)

        # Send narrate_range (accepted anytime, not just when paused)
        await ws.send(json.dumps({
            "type": "narrate_range",
            "start_turn": 1,
            "end_turn": 1,
        }))

        # Read response — spy intercepts narrate_batch, so we get narration_complete
        # with empty entries or possibly no response if curate returns nothing.
        # Give it a moment to process.
        try:
            resp_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            pass  # spy returns [] so no narration_complete sent — that's fine

    # great_persons kwarg should be present
    assert "great_persons" in captured_kwargs
    # agent_name_map should be present and contain our test GP
    assert "agent_name_map" in captured_kwargs
    if captured_kwargs["agent_name_map"] is not None:
        assert 42 in captured_kwargs["agent_name_map"]
        assert captured_kwargs["agent_name_map"][42] == "Kiran"
    # Bridge-only inputs should be None
    assert captured_kwargs.get("social_edges") is None
    assert captured_kwargs.get("dynasty_registry") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_live_integration.py::test_narrate_range_passes_great_persons_and_agent_name_map -v`
Expected: FAIL — current call at `live.py:628` passes no kwargs.

- [ ] **Step 3: Wire great_persons, agent_name_map, and explicit None kwargs into narrate_range**

In `src/chronicler/live.py`, modify the narrate_range handler at ~line 598-628. After the existing `named_chars` collection (line 606-610), add GP reconstruction and wire into the narrate_batch call.

After the `named_chars` block (~line 610), add great_persons reconstruction:

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

Then update the narrate_batch call at line 628:

Old:
```python
                            entries = engine.narrate_batch(moments, all_history)
```

New:
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
