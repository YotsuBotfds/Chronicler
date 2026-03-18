# M44: API Narration Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Claude Sonnet 4.6 as the primary narrator for curated chronicle moments via `--narrator api`, with token tracking and bundle metadata.

**Architecture:** Extend `create_clients()` with a `narrator` parameter. In API mode, `execute_run()` skips per-turn narration and reflections, runs curator + `narrate_batch()` post-loop before bridge close. Token accumulators on `AnthropicClient` provide cost visibility. `_run_narrate()` gets the same client swap with no flow changes.

**Tech Stack:** Python 3.12, `anthropic` SDK (optional dependency), existing `LLMClient` protocol.

**Spec:** `docs/superpowers/specs/2026-03-18-m44-api-narration-design.md`

---

### Task 1: AnthropicClient Token Tracking

**Files:**
- Modify: `src/chronicler/llm.py:61-81` (AnthropicClient class)
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write failing tests for token accumulators**

```python
# In tests/test_llm.py, add to TestAnthropicClient:

def test_token_tracking_accumulators(self):
    """AnthropicClient tracks input/output tokens and call count."""
    mock_sdk = MagicMock()
    mock_sdk.messages.create.return_value = MagicMock(
        content=[MagicMock(text="The empire rose...")],
        usage=MagicMock(input_tokens=150, output_tokens=80),
    )
    client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

    assert client.total_input_tokens == 0
    assert client.total_output_tokens == 0
    assert client.call_count == 0

    client.complete("Write a chronicle entry", max_tokens=500)

    assert client.total_input_tokens == 150
    assert client.total_output_tokens == 80
    assert client.call_count == 1

def test_token_tracking_accumulates_across_calls(self):
    """Token counts accumulate across multiple API calls."""
    mock_sdk = MagicMock()
    mock_sdk.messages.create.side_effect = [
        MagicMock(
            content=[MagicMock(text="First entry...")],
            usage=MagicMock(input_tokens=100, output_tokens=50),
        ),
        MagicMock(
            content=[MagicMock(text="Second entry...")],
            usage=MagicMock(input_tokens=200, output_tokens=100),
        ),
    ]
    client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

    client.complete("First")
    client.complete("Second")

    assert client.total_input_tokens == 300
    assert client.total_output_tokens == 150
    assert client.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py::TestAnthropicClient -v`
Expected: FAIL — `AnthropicClient` has no `total_input_tokens` attribute.

- [ ] **Step 3: Add token tracking to AnthropicClient**

In `src/chronicler/llm.py`, modify `AnthropicClient`:

```python
class AnthropicClient:
    """Anthropic SDK client for Claude API calls.

    Optional — requires `pip install chronicler[api]`.
    """

    def __init__(self, client: Any, model: str = "claude-sonnet-4-6"):
        self.model = model
        self._client = client
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.call_count: int = 0

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens
        self.call_count += 1
        return response.content[0].text.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py::TestAnthropicClient -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/llm.py tests/test_llm.py
git commit -m "feat(m44): add token tracking accumulators to AnthropicClient"
```

---

### Task 2: Extend `create_clients()` with Narrator Mode

**Files:**
- Modify: `src/chronicler/llm.py:84-109` (create_clients function)
- Test: `tests/test_llm.py`

- [ ] **Step 1: Write failing tests for narrator parameter**

```python
# In tests/test_llm.py, add to TestCreateClients:

def test_narrator_api_returns_anthropic_client(self):
    """When narrator='api', narrative client is AnthropicClient."""
    # Mock the anthropic import at module level
    import unittest.mock as mock
    mock_anthropic_module = MagicMock()
    mock_anthropic_instance = MagicMock()
    mock_anthropic_module.Anthropic.return_value = mock_anthropic_instance

    with mock.patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
        _, narrative_client = create_clients(narrator="api")
        assert isinstance(narrative_client, AnthropicClient)
        assert narrative_client.model == "claude-sonnet-4-6"

def test_narrator_api_with_custom_model(self):
    """--narrative-model flows through to AnthropicClient."""
    import unittest.mock as mock
    mock_anthropic_module = MagicMock()
    mock_anthropic_instance = MagicMock()
    mock_anthropic_module.Anthropic.return_value = mock_anthropic_instance

    with mock.patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
        _, narrative_client = create_clients(
            narrator="api", narrative_model="claude-opus-4-6"
        )
        assert narrative_client.model == "claude-opus-4-6"

def test_narrator_local_unchanged(self):
    """narrator='local' produces same result as default."""
    sim, narr = create_clients(narrator="local")
    assert isinstance(narr, LocalNarrativeClient)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py::TestCreateClients::test_narrator_api_returns_anthropic_client -v`
Expected: FAIL — `create_clients()` doesn't accept `narrator` parameter.

- [ ] **Step 3: Add narrator parameter to create_clients**

In `src/chronicler/llm.py`, modify `create_clients()`:

```python
def create_clients(
    local_url: str = DEFAULT_LOCAL_URL,
    sim_model: str | None = None,
    narrative_model: str | None = None,
    narrator: str = "local",
) -> tuple[LLMClient, LLMClient]:
    """Create simulation and narrative clients.

    sim_client always routes to local LM Studio (free, high volume).
    narrative_client routes to local or Anthropic API based on narrator mode.
    """
    sim_client: LLMClient = LocalClient(
        base_url=local_url,
        model=sim_model or "",
        temperature=0.3,
    )

    if narrator == "api":
        import anthropic
        narrative_client: LLMClient = AnthropicClient(
            client=anthropic.Anthropic(),
            model=narrative_model or "claude-sonnet-4-6",
        )
    else:
        narrative_client = LocalNarrativeClient(
            base_url=local_url,
            model=narrative_model or "",
            temperature=0.8,
        )

    return sim_client, narrative_client
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py::TestCreateClients -v`
Expected: PASS (all tests including existing ones)

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/llm.py tests/test_llm.py
git commit -m "feat(m44): add narrator mode parameter to create_clients()"
```

---

### Task 3: CLI Argument and Validation

**Files:**
- Modify: `src/chronicler/main.py:596-680` (_build_parser), `src/chronicler/main.py:758-810` (main validation block)
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing tests for --narrator argument and validation**

```python
# In tests/test_main.py, add:

import pytest
from unittest.mock import patch
from chronicler.main import _build_parser


class TestNarratorArgument:
    def test_narrator_default_is_local(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.narrator == "local"

    def test_narrator_api(self):
        parser = _build_parser()
        args = parser.parse_args(["--narrator", "api"])
        assert args.narrator == "api"

    def test_narrator_invalid_choice(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--narrator", "invalid"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_main.py::TestNarratorArgument -v`
Expected: FAIL — `_build_parser()` doesn't have `--narrator`.

- [ ] **Step 3: Add --narrator argument to _build_parser**

In `src/chronicler/main.py`, add after the `--narrate-output` argument (line 679):

```python
    parser.add_argument("--narrator", type=str, default="local",
                        choices=["local", "api"],
                        help="Narrator backend: local (LM Studio) or api (Claude API)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_main.py::TestNarratorArgument -v`
Expected: PASS

- [ ] **Step 5: Add validation checks to main()**

In `src/chronicler/main.py`, in `main()`, add **above** the `--narrate` early return (before line 808). Insert after the `--seed-range` block (after line 802):

```python
    # --- M44: --narrator api validation ---
    if getattr(args, "narrator", "local") == "api":
        if getattr(args, "simulate_only", False):
            print("Error: --narrator api and --simulate-only are contradictory", file=sys.stderr)
            sys.exit(1)
        if args.live:
            print("Error: --narrator api is incompatible with --live (API latency)", file=sys.stderr)
            sys.exit(1)
        if args.parallel is not None and args.batch:
            print("Error: --narrator api is incompatible with --batch --parallel", file=sys.stderr)
            sys.exit(1)
        try:
            import anthropic  # noqa: F401
        except ImportError:
            print("Error: --narrator api requires the anthropic package. "
                  "Install with: pip install chronicler[api]", file=sys.stderr)
            sys.exit(1)
        import os
        if "ANTHROPIC_API_KEY" not in os.environ:
            print("Error: --narrator api requires ANTHROPIC_API_KEY environment variable",
                  file=sys.stderr)
            sys.exit(1)
```

- [ ] **Step 6: Write validation tests**

```python
# In tests/test_main.py, add:

import sys
from unittest.mock import patch
from chronicler.main import main


class TestNarratorValidation:
    def test_narrator_api_with_simulate_only_exits(self):
        """--narrator api + --simulate-only is contradictory."""
        with patch("sys.argv", ["chronicler", "--narrator", "api", "--simulate-only"]):
            with pytest.raises(SystemExit):
                main()

    def test_narrator_api_with_live_exits(self):
        """--narrator api + --live is incompatible."""
        with patch("sys.argv", ["chronicler", "--narrator", "api", "--live"]):
            with pytest.raises(SystemExit):
                main()

    def test_narrator_api_with_batch_parallel_exits(self):
        """--narrator api + --batch --parallel is incompatible."""
        with patch("sys.argv", ["chronicler", "--narrator", "api",
                                "--batch", "10", "--parallel"]):
            with pytest.raises(SystemExit):
                main()
```

- [ ] **Step 7: Thread narrator to create_clients calls**

In `main()`, update the `create_clients()` call (line 817-821):

```python
            sim_client, narrative_client = create_clients(
                local_url=args.local_url,
                sim_model=args.sim_model,
                narrative_model=args.narrative_model,
                narrator=args.narrator,
            )
```

In `_run_narrate()`, update the `create_clients()` call (line 705-709):

```python
    sim_client, narrative_client = create_clients(
        local_url=args.local_url,
        sim_model=getattr(args, "sim_model", None),
        narrative_model=getattr(args, "narrative_model", None),
        narrator=getattr(args, "narrator", "local"),
    )
```

Note: `args.narrator` is used directly in `main()` (always present after parser change), but `getattr` is used in `_run_narrate()` for backward compatibility with callers that may construct their own args namespace without the new field.

- [ ] **Step 8: Commit**

```bash
git add src/chronicler/main.py tests/test_main.py
git commit -m "feat(m44): add --narrator CLI argument with validation"
```

---

### Task 4: Narration Path Routing in `execute_run()`

**Files:**
- Modify: `src/chronicler/main.py:89-92` (client setup), `src/chronicler/main.py:340-406` (per-turn narration + reflection), `src/chronicler/main.py:427-552` (post-loop compile + bundle)
- Test: `tests/test_main.py`

This is the core task: in API mode, skip per-turn narration and reflections, run curator + `narrate_batch()` post-loop.

- [ ] **Step 1: Determine API mode flag and set noop narrator in execute_run**

Add the import at the top of the file if not already present:

```python
from chronicler.llm import DEFAULT_LOCAL_URL, LLMClient, AnthropicClient, create_clients
```

At the top of `execute_run()`, after line 91 (`_narr = narrative_client or _DummyClient()`):

```python
    _api_mode = isinstance(_narr, AnthropicClient)
```

Then extend the existing `_noop_narrator` pattern (lines 122-127). The narrator callback is passed into `run_turn()` — it's not called directly in `execute_run()`. The existing `--simulate-only` pattern already sets `_noop_narrator`:

```python
    # In simulate-only mode, replace narrator with a no-op
    _simulate_only = getattr(args, "simulate_only", False)
    if _simulate_only or _api_mode:
        _noop_narrator = lambda world, events: ""
    else:
        _noop_narrator = None
```

This gates per-turn narration at the same point `--simulate-only` does. No need to find where `chronicle_text` is assigned — `run_turn()` receives the noop callback and returns `""`.

- [ ] **Step 2: Initialize gap_summaries for both code paths**

After the `era_reflections` initialization (line 212), add:

```python
    gap_summaries = None  # Set by curated narration in API mode
```

This prevents `NameError` in the `assemble_bundle()` call when `_api_mode` is False.

- [ ] **Step 3: Gate off reflections in API mode**

Wrap the existing `should_reflect` block (lines 391-407) with the API mode check:

```python
        # Generate era reflections at intervals (skip in API mode)
        if not _api_mode and should_reflect(world.turn, interval=reflection_interval):
```

This keeps `era_reflections` empty. Memory streams still accumulate (line 383-388, before this block).

- [ ] **Step 4: Add post-loop curated narration**

After the simulation loop ends and **before** `agent_bridge.close()` (before line 428), insert:

```python
    # M44: Post-loop curated narration for API mode
    if _api_mode:
        from chronicler.curator import curate

        # Collect named character names for curator scoring
        named_chars = set()
        for gp_list in (getattr(civ, "great_persons", []) for civ in world.civilizations):
            for gp in gp_list:
                if gp.active and gp.agent_id is not None:
                    named_chars.add(gp.name)

        moments, gap_summaries = curate(
            events=world.events_timeline,
            named_events=world.named_events,
            history=history,
            budget=getattr(args, "budget", 50),
            seed=seed,
            named_characters=named_chars if named_chars else None,
        )

        def progress_cb(completed: int, total: int, eta: float | None) -> None:
            eta_str = f" (ETA: {eta:.1f}s)" if eta is not None else ""
            print(f"  Narrating {completed}/{total}{eta_str}")

        chronicle_entries = engine.narrate_batch(
            moments, history, gap_summaries, on_progress=progress_cb,
        )

        print(f"API narration: curated {len(moments)} moments from {len(world.events_timeline)} events")
```

Note: `gap_summaries` is created here and used below in `assemble_bundle()`.

- [ ] **Step 5: Thread gap_summaries to compile_chronicle and assemble_bundle**

In API mode, `chronicle_entries` is already replaced by the post-loop block above. `gap_summaries` needs to flow to both output paths.

First, update `compile_chronicle()` (line 437-442). It already accepts `gap_summaries` (chronicle.py:16) and uses them to insert one-liner summaries between curated entries. Without this, the .md output jumps between curated moments with no indication of what happened in between:

```python
    output_text = compile_chronicle(
        world_name=world.name,
        entries=chronicle_entries,
        era_reflections=era_reflections,
        epilogue=epilogue,
        gap_summaries=gap_summaries,
    )
```

Then update `assemble_bundle()` (line 541-549):

```python
    bundle = assemble_bundle(
        world=world,
        history=history,
        chronicle_entries=chronicle_entries,
        era_reflections=era_reflections,
        sim_model=sim_model_name,
        narrative_model=narr_model_name,
        interestingness_score=score_run(result, interestingness_weights),
        gap_summaries=gap_summaries,
    )
```

`gap_summaries` was initialized to `None` in Step 2 and overwritten by the curated narration block in API mode. Both `compile_chronicle()` and `assemble_bundle()` already handle `None` gracefully.

- [ ] **Step 6: Run existing tests to verify no regression**

Run: `pytest tests/test_main.py -v`
Expected: All existing tests PASS (API mode is opt-in, default behavior unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/chronicler/main.py
git commit -m "feat(m44): API narration path in execute_run — noop per-turn, curated post-loop"
```

---

### Task 5: Token Summary and Bundle Metadata

**Files:**
- Modify: `src/chronicler/main.py` (execute_run post-narration, _run_narrate output dict)
- Test: `tests/test_llm.py` (token summary format test)

- [ ] **Step 1: Add token summary to execute_run**

After the curated narration block in `execute_run()` (the API mode block from Task 4), add:

```python
        # Token usage summary
        if isinstance(_narr, AnthropicClient):
            inp = _narr.total_input_tokens
            out = _narr.total_output_tokens
            print(f"API narration: {_narr.call_count} calls, "
                  f"{inp/1000:.1f}K input + {out/1000:.1f}K output tokens")
```

- [ ] **Step 2: Add narrator_mode and token fields to bundle metadata**

In `execute_run()`, after the `assemble_bundle()` call, add metadata fields:

```python
    # M44: narrator provenance metadata
    bundle["metadata"]["narrator_mode"] = "api" if _api_mode else "local"
    if isinstance(_narr, AnthropicClient):
        bundle["metadata"]["api_input_tokens"] = _narr.total_input_tokens
        bundle["metadata"]["api_output_tokens"] = _narr.total_output_tokens
```

- [ ] **Step 3: Add token summary and metadata to _run_narrate**

In `_run_narrate()`, after the `narrate_batch()` call (line 739), add token summary:

```python
    # M44: Token summary and metadata
    if isinstance(narrative_client, AnthropicClient):
        inp = narrative_client.total_input_tokens
        out = narrative_client.total_output_tokens
        print(f"API narration: {narrative_client.call_count} calls, "
              f"{inp/1000:.1f}K input + {out/1000:.1f}K output tokens")
```

In `_run_narrate()`'s output dict (line 746-750), update metadata:

```python
    result = {
        "chronicle_entries": [entry.model_dump() for entry in chronicle_entries],
        "gap_summaries": [gs.model_dump() for gs in gap_summaries],
        "metadata": bundle.get("metadata", {}),
    }
    # M44: narrator provenance
    result["metadata"]["narrator_mode"] = getattr(args, "narrator", "local")
    if isinstance(narrative_client, AnthropicClient):
        result["metadata"]["api_input_tokens"] = narrative_client.total_input_tokens
        result["metadata"]["api_output_tokens"] = narrative_client.total_output_tokens
```

Add the `AnthropicClient` import at the top of `main.py` (already done in Task 4).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_llm.py tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/main.py
git commit -m "feat(m44): token usage summary and narrator_mode bundle metadata"
```

---

### Task 6: First-Failure Warning in narrate_batch

**Files:**
- Modify: `src/chronicler/narrative.py:840-850` (except block)
- Test: `tests/test_narrative.py`

- [ ] **Step 1: Write failing test for warning on narration failure**

```python
# In tests/test_narrative.py, add:

import logging

def test_narrate_batch_warns_on_first_failure(caplog):
    """narrate_batch logs a warning on the first LLM failure."""
    from unittest.mock import MagicMock
    from chronicler.narrative import NarrativeEngine
    from chronicler.models import NarrativeMoment, NarrativeRole, Event, TurnSnapshot

    mock_client = MagicMock()
    mock_client.complete.side_effect = Exception("API error")
    mock_client.model = "test"

    engine = NarrativeEngine(
        sim_client=MagicMock(model="test"),
        narrative_client=mock_client,
    )

    moment = NarrativeMoment(
        events=[Event(
            event_type="war", description="A war happened",
            actors=["Civ1"], importance=7, turn=10, source="simulation",
        )],
        named_events=[],
        turn_range=(10, 10),
        anchor_turn=10,
        score=7.0,
        narrative_role=NarrativeRole.CLIMAX,
        causal_links=[],
    )
    history = [TurnSnapshot(turn=10, civ_stats={}, region_control={})]

    with caplog.at_level(logging.WARNING):
        entries = engine.narrate_batch([moment], history, [])

    assert len(entries) == 1
    assert "API error" in caplog.text or "narration failed" in caplog.text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_narrative.py::test_narrate_batch_warns_on_first_failure -v`
Expected: FAIL — no warning logged.

- [ ] **Step 3: Add logger.warning to the except block**

In `src/chronicler/narrative.py`, add at the top of the file (if not present):

```python
import logging
logger = logging.getLogger(__name__)
```

In `narrate_batch()`, add a local variable before the `for idx, moment` loop (around line 713):

```python
        _first_failure = True
```

Modify the except block (line 845-850):

```python
            except Exception as exc:
                # Log first failure per narrate_batch call for visibility
                if _first_failure:
                    logger.warning("Narration failed (falling back to mechanical summary): %s", exc)
                    _first_failure = False
                # Mechanical fallback: join event descriptions
                descriptions = [
                    e.description for e in moment.events if e.description
                ]
                narrative = "; ".join(descriptions) if descriptions else "Events unfolded."
```

Using a local variable instead of a `self` attribute ensures the warning fires once per `narrate_batch()` call — in sequential batch mode, each seed gets its own warning if narration fails.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_narrative.py::test_narrate_batch_warns_on_first_failure -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chronicler/narrative.py tests/test_narrative.py
git commit -m "feat(m44): log warning on first narration failure in narrate_batch"
```

---

### Task 7: Integration Test — End-to-End API Mode

**Files:**
- Test: `tests/test_main.py`

This test verifies the full flow: `execute_run()` with a mocked `AnthropicClient` produces curated entries, skips reflections, and writes correct metadata.

- [ ] **Step 1: Write integration test**

```python
# In tests/test_main.py, add:

from unittest.mock import MagicMock, patch
from chronicler.main import execute_run
from chronicler.llm import AnthropicClient
import argparse
import tempfile
import json
from pathlib import Path


class TestApiNarrationIntegration:
    def _make_args(self, tmp_dir):
        """Build minimal args namespace for a short API-mode run."""
        return argparse.Namespace(
            seed=42,
            turns=20,
            civs=3,
            regions=6,
            output=str(Path(tmp_dir) / "chronicle.md"),
            state=str(Path(tmp_dir) / "state.json"),
            resume=None,
            reflection_interval=10,
            llm_actions=False,
            scenario=None,
            simulate_only=False,
            agents="off",
            tuning=None,
            aggression_bias=None,
            tech_diffusion_rate=None,
            resource_abundance=None,
            trade_friction=None,
            severity_multiplier=None,
            cultural_drift_speed=None,
            religion_intensity=None,
            secession_likelihood=None,
            budget=50,
            narrator="api",
        )

    def test_api_mode_produces_curated_entries_with_metadata(self):
        """execute_run with API narrator: curated narration, no reflections, metadata written."""
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = MagicMock(
            content=[MagicMock(text="The great empire rose from humble beginnings...")],
            usage=MagicMock(input_tokens=500, output_tokens=200),
        )
        api_client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")

        with tempfile.TemporaryDirectory() as tmp_dir:
            args = self._make_args(tmp_dir)
            result = execute_run(
                args,
                sim_client=MagicMock(model="test", complete=MagicMock(return_value="DEVELOP")),
                narrative_client=api_client,
            )

            # Bundle was written
            bundle_path = Path(tmp_dir) / "chronicle_bundle.json"
            assert bundle_path.exists()

            bundle = json.loads(bundle_path.read_text())

            # Metadata has narrator_mode and token counts
            meta = bundle["metadata"]
            assert meta["narrator_mode"] == "api"
            assert "api_input_tokens" in meta
            assert "api_output_tokens" in meta
            assert meta["api_input_tokens"] > 0

            # Era reflections should be empty (gated off in API mode)
            assert bundle.get("era_reflections", {}) == {} or all(
                v == "" for v in bundle.get("era_reflections", {}).values()
            )

            # API client was called for curated moments, not per-turn (20 turns)
            call_count = mock_sdk.messages.create.call_count
            assert call_count < 20, (
                f"Expected curated narration (< 20 calls), got {call_count} "
                "(suggests per-turn narration was not skipped)"
            )

            # Gap summaries should be present in bundle
            assert "gap_summaries" in bundle
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_main.py::TestApiNarrationIntegration -v`
Expected: PASS (if all prior tasks are implemented). If it fails, debug — this is the integration verification.

- [ ] **Step 3: Write _run_narrate integration test**

```python
# In tests/test_main.py, add to TestApiNarrationIntegration:

    def test_run_narrate_api_mode_writes_metadata(self):
        """_run_narrate with --narrator api writes narrator_mode and token fields."""
        import tempfile
        import json
        from pathlib import Path
        from unittest.mock import MagicMock, patch
        from chronicler.main import _run_narrate
        from chronicler.llm import AnthropicClient

        # Create a minimal simulate-only bundle to narrate
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = MagicMock(
            content=[MagicMock(text="The chronicles speak of great change...")],
            usage=MagicMock(input_tokens=300, output_tokens=150),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            # First, generate a simulate-only bundle
            from chronicler.main import execute_run
            sim_args = argparse.Namespace(
                seed=42, turns=20, civs=3, regions=6,
                output=str(Path(tmp_dir) / "chronicle.md"),
                state=str(Path(tmp_dir) / "state.json"),
                resume=None, reflection_interval=10,
                llm_actions=False, scenario=None,
                simulate_only=True, agents="off", tuning=None,
                aggression_bias=None, tech_diffusion_rate=None,
                resource_abundance=None, trade_friction=None,
                severity_multiplier=None, cultural_drift_speed=None,
                religion_intensity=None, secession_likelihood=None,
                budget=50, narrator="local",
            )
            execute_run(sim_args)

            bundle_path = Path(tmp_dir) / "chronicle_bundle.json"
            assert bundle_path.exists()

            # Now re-narrate with --narrator api
            narrate_args = argparse.Namespace(
                narrate=bundle_path,
                narrator="api",
                local_url="http://localhost:1234/v1",
                sim_model=None,
                narrative_model=None,
                budget=10,
                narrate_output=Path(tmp_dir) / "narrated.json",
            )

            # Patch create_clients to return our mocked API client
            api_client = AnthropicClient(client=mock_sdk, model="claude-sonnet-4-6")
            with patch("chronicler.main.create_clients",
                       return_value=(MagicMock(model="test"), api_client)):
                _run_narrate(narrate_args)

            # Check output metadata
            output = json.loads((Path(tmp_dir) / "narrated.json").read_text())
            assert output["metadata"]["narrator_mode"] == "api"
            assert output["metadata"]["api_input_tokens"] > 0
            assert output["metadata"]["api_output_tokens"] > 0
```

- [ ] **Step 4: Run both integration tests**

Run: `pytest tests/test_main.py::TestApiNarrationIntegration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_main.py
git commit -m "test(m44): integration tests for execute_run and _run_narrate API mode"
```

---

### Task 8: Full Test Suite Verification

- [ ] **Step 1: Run full Python test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS. No regressions — API mode is opt-in, default behavior (`narrator="local"`) is unchanged.

- [ ] **Step 2: Verify --narrator local is bit-identical**

Run a short simulation with `--narrator local` and verify output matches pre-M44 behavior:

```bash
python -m chronicler --seed 42 --turns 20 --civs 3 --regions 6 --simulate-only --output output/test_local.md
```

Expected: Runs without errors, same as before M44.

- [ ] **Step 3: Commit any fixes if needed, then tag**

```bash
git add -A
git commit -m "fix(m44): test suite fixes" # only if needed
```
