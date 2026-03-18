# M44: API Narration Pipeline — Design Spec

> **Status:** Draft
> **Author:** Cici (Claude Opus 4.6)
> **Date:** 2026-03-18
> **Prerequisites:** M43b merged. All narration infrastructure in place.

---

## Goal

Wire Claude Sonnet 4.6 as the primary narrator for curated chronicle moments, with local LLM as fallback. Token usage tracked for cost visibility. Quality validated via controlled 20-seed comparison.

---

## Architecture Overview

The two-client architecture is already clean: `sim_client` stays local (free, high volume action selection), only `narrative_client` switches to API. `AnthropicClient` already exists in `llm.py` and implements the `LLMClient` protocol.

**Key insight:** `--narrator api` does NOT narrate every turn. The per-turn `generate_chronicle()` path exists because local inference is free. API narration uses the curated `narrate_batch()` pipeline — curator selects 10-20 moments, only those get API calls. Cost: ~$0.15-0.30 per 500-turn chronicle at Sonnet 4.6 pricing.

---

## 1. CLI & Validation

### New Argument

`--narrator` added to `_build_parser()`:
- Choices: `["local", "api"]`
- Default: `"local"`

### Validation Block (in `main()`, before any dispatch)

All validation runs before any dispatch — critically, **above the `_run_narrate()` early return** in `main()`. The `--narrate` path currently early-returns before the general validation block, so these checks must precede it:

1. **`--narrator api` + `--simulate-only`** — contradictory, argument error, exit.
2. **`--narrator api` + `--live`** — API latency incompatible with WebSocket live mode, argument error, exit.
3. **`--narrator api` + `import anthropic` fails** — error: `"--narrator api requires the anthropic package. Install with: pip install chronicler[api]"`, exit.
4. **`--narrator api` + `ANTHROPIC_API_KEY` not in `os.environ`** — error: `"--narrator api requires ANTHROPIC_API_KEY environment variable"`, exit.
5. **`--narrator api` + `--batch --parallel`** — parallel workers can't share API clients or token tracking, argument error, exit.

### `--narrative-model` Interaction

- `--narrator local`: `--narrative-model` flows to `LocalNarrativeClient` (LM Studio model selection). Default: LM Studio's loaded model.
- `--narrator api`: `--narrative-model` flows to `AnthropicClient(model=...)`. Default: `claude-sonnet-4-6`.

---

## 2. Client Factory

`create_clients()` in `llm.py` gains a `narrator: str = "local"` parameter. When `narrator="api"`:

```python
def create_clients(
    local_url: str = DEFAULT_LOCAL_URL,
    sim_model: str | None = None,
    narrative_model: str | None = None,
    narrator: str = "local",
) -> tuple[LLMClient, LLMClient]:
```

- Imports `anthropic`, constructs `Anthropic()` client.
- Returns `AnthropicClient(client=anthropic.Anthropic(), model=narrative_model or "claude-sonnet-4-6")` as the narrative client.
- `sim_client` is always `LocalClient` (action selection stays local and free).
- **No validation in the factory** — `create_clients()` trusts that `main()` already validated import availability and API key presence. CLI-level concerns (`sys.exit`, user-facing error messages) don't belong in a library-level factory.

---

## 3. Token Usage Tracking

### AnthropicClient Accumulators

Three fields added to `AnthropicClient.__init__()`:

```python
self.total_input_tokens: int = 0
self.total_output_tokens: int = 0
self.call_count: int = 0
```

`complete()` reads `response.usage.input_tokens` and `response.usage.output_tokens` from the API response object (free data, already returned by the Anthropic API), increments accumulators.

### Console Summary

`execute_run()` and `_run_narrate()` check `isinstance(narrative_client, AnthropicClient)` after narration completes and print:

```
API narration: 15 calls, 42.1K input + 28.4K output tokens
```

### Bundle Metadata

New fields in bundle metadata:

- `narrator_mode`: `"api"` or `"local"` — provenance for quality comparison filtering.
- `api_input_tokens`: total input tokens (API mode only).
- `api_output_tokens`: total output tokens (API mode only).

Written in both paths:
- `assemble_bundle()` in `execute_run()` — alongside existing `narrative_model`.
- `_run_narrate()`'s output dict — in the `result["metadata"]` update, alongside the isinstance check.

---

## 4. Narration Path Routing

### `execute_run()` with `--narrator api`

1. `NarrativeEngine(sim_client=local_client, narrative_client=anthropic_client)` — API client lives on the engine.
2. Simulation loop: per-turn narrator callback is `lambda w, e: ""` (noop). No per-turn prose, no API calls during simulation.
3. **After simulation loop, before `agent_bridge.close()`:** curator selects moments from accumulated history/events, then `engine.narrate_batch()` narrates curated moments via `AnthropicClient`.
4. **Curated entries replace the per-turn list.** The simulation loop builds `chronicle_entries` with `narrative=""` (from the noop lambda). The curated `narrate_batch()` output replaces this list before `assemble_bundle()` is called — the empty per-turn entries have no value. `gap_summaries` from `curate()` are threaded into `assemble_bundle()` (which already accepts `gap_summaries: list[GapSummary] | None`).
5. Positioning before bridge close preserves the option to thread agent context (social edges, agent name map, gini) into narration in a future milestone. For M44, agent context matches `_run_narrate()` level (limited — pre-existing gap, not M44 scope).
6. Token summary printed after narration completes.

### `execute_run()` with `--narrator local` (default)

Unchanged. Per-turn narration via local model, same behavior as today.

### `_run_narrate()` with `--narrator api`

Unchanged flow — loads bundle, curates, narrates. Uses `AnthropicClient` instead of `LocalNarrativeClient`. Token counts and `narrator_mode` written to output metadata.

### `--narrator api` + `--batch`

Each seed in the batch runs the API-mode `execute_run()` path. In **sequential batch** mode, the shared `AnthropicClient` instance accumulates tokens across seeds; summary printed at end of batch. In **parallel batch** mode (`--parallel`), `multiprocessing.Pool` workers don't share client objects — each worker would need its own `AnthropicClient`, and per-worker token counts are lost when the process exits. `--narrator api` + `--batch --parallel` should be a validation error (parallel batch is for simulation throughput; API narration adds latency that defeats the purpose).

---

## 5. ERA_REGISTER Prompt Design

### Pre-M44 Experiment (Informs Implementation)

Four-condition A/B test using existing bundle data and manual API calls. Does NOT require M44 pipeline.

| Condition | Model | Register Style |
|-----------|-------|---------------|
| 1 | Claude Sonnet 4.6 | Full ERA_REGISTER (detailed voice + style instructions) |
| 2 | Claude Sonnet 4.6 | Light register (e.g., "Write as a medieval chronicler" — one sentence) |
| 3 | Local (Qwen 3 235B) | Full ERA_REGISTER (baseline) |
| 4 | Local (Qwen 3 235B) | Light register |

10 seeds, same moments per seed, side-by-side scoring on: prose quality, character continuity, era-appropriate voice, emotional resonance.

### Outcome Determines M44 Prompt Path

- **Lighter wins for both models** → single simplified register dict, replaces `ERA_REGISTER`. One code path.
- **Lighter wins for Claude, local regresses** → two dicts: `ERA_REGISTER` for local, `API_ERA_REGISTER` for API. Selection in `narrate_batch()` where `era_voice, era_style` are already looked up — swap the dict based on narrator mode. ~3-line change.
- **Full register wins for both** → no change, keep `ERA_REGISTER` as-is.

### Architecture

The lookup is a single dict access in `narrate_batch()`. Adding a second dict and a conditional is trivial. No pre-architecture needed — the experiment result determines the implementation.

---

## 6. Quality Comparison (M44 Deliverable)

### Primary Comparison (Controlled)

Isolates model quality as the only variable:

1. Run 20 seeds with `--simulate-only` (fast, free, deterministic).
2. `--narrate <bundle> --narrator local` — curated pipeline, local model.
3. `--narrate <bundle> --narrator api` — same curated pipeline, same prompts, API model.
4. Moment-by-moment scoring.

Same pipeline, same prompt content, same moments. Only the LLM varies. Scientifically valid.

### Scoring Dimensions

Per the roadmap:
- Prose quality (grammar, vocabulary, flow)
- Character continuity (named characters referenced correctly)
- Era-appropriate voice
- Emotional resonance

### Output

Written report documenting findings, filed in `docs/superpowers/analytics/`.

### Secondary Check (Optional)

A handful of seeds via `execute_run()` with each narrator mode. End-to-end UX validation ("does the product feel better?"), not a model comparison. Not a formal deliverable.

---

## 7. Failure Handling

### Startup Failures

All caught in `main()` validation block before simulation starts:

| Failure | Behavior |
|---------|----------|
| `anthropic` not installed | Error message with install instructions, exit |
| `ANTHROPIC_API_KEY` missing | Error message, exit |
| Contradictory flags (`--simulate-only`, `--live`) | Argument error, exit |

### Runtime Failures

Handled by existing `narrate_batch()` per-moment exception handling:

| Failure | Behavior |
|---------|----------|
| Invalid API key (AuthenticationError) | First moment falls back to mechanical summary; error visible in output |
| Rate limit (RateLimitError) | Per-moment fallback, batch continues |
| Network error | Per-moment fallback, batch continues |
| Transient API error | Per-moment fallback, batch continues |

No new error handling needed — `narrate_batch()` already wraps each `complete()` call in try/except with mechanical fallback.

---

## 8. Scope Boundaries

### In Scope

- `--narrator` CLI argument with validation
- `create_clients()` narrator mode parameter
- `AnthropicClient` token tracking (accumulators, console summary, bundle metadata)
- `execute_run()` API narration path (noop per-turn, post-loop curated narration)
- `narrator_mode` bundle metadata field
- ERA_REGISTER A/B experiment (pre-implementation)
- 20-seed controlled quality comparison (post-implementation)
- Written reports for both experiments

### Out of Scope

- `_run_narrate()` agent context threading — pre-existing gap, not M44.
- Cost guardrails, dry-run mode, batch confirmation prompts — operator trust model.
- Dollar cost estimation — prices change, token counts are factual.
- Live mode API support — latency incompatible.
- `_DummyClient` changes — existing behavior preserved.

### No Rust Changes

Entirely Python-side. No FFI, no agent pool, no satisfaction formula changes.

### No 200-Seed Simulation Regression

M44 does not change simulation mechanics. The `--agents=off` bit-identical guarantee is unaffected. Simulation output is unchanged regardless of narrator mode. The 20-seed quality comparison is the appropriate validation for this milestone.

---

## 9. Testing Strategy

### Unit Tests

- `AnthropicClient` token accumulation (mock API response with usage fields).
- `create_clients(narrator="api")` returns `AnthropicClient` as narrative client.
- `create_clients(narrator="local")` returns `LocalNarrativeClient` (unchanged behavior).
- Validation error cases: `--narrator api` + `--simulate-only`, `--narrator api` + `--live`, `--narrator api` + `--batch --parallel`.

### Integration Tests

- `execute_run()` with `--narrator api` (mocked `AnthropicClient`): verify noop per-turn narration, post-loop curated narration, token summary in metadata.
- `_run_narrate()` with `--narrator api` (mocked): verify `narrator_mode` and token fields in output metadata.
- Bundle metadata roundtrip: `narrator_mode` survives save/load.

### Manual Validation

- ERA_REGISTER A/B experiment (10 seeds, 4 conditions).
- Quality comparison (20 seeds, controlled pipeline).

---

## 10. Cost Model

| Scenario | Moments | Estimated Cost |
|----------|---------|---------------|
| Single 500-turn run | 10-20 | $0.15-0.30 |
| 20-seed quality comparison | 200-400 | $3-6 |
| Accidental `--batch 200 --narrator api` | 2000-4000 | $30-60 |

The 200-seed regression scenario is a user error — regression tests simulation mechanics (`--simulate-only`), not prose quality. Token tracking provides visibility. No guardrails needed.

---

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | No `--batch` sub-mode | `narrate_batch()` already processes sequentially with `previous_prose` threading. Roadmap description predates that implementation. |
| 2 | Hard fail at startup for missing package/key | User explicitly requested API narration; silent fallback would be confusing. Failing after a long simulation wastes time. |
| 3 | All validation in `main()`, not in factory | CLI concerns (user-facing messages, `sys.exit`) don't belong in library-level code. Tests and `run_chronicle()` callers shouldn't get `sys.exit`. |
| 4 | Token tracking, no dollar estimates | API pricing changes. Token counts are factual. Operator multiplies. |
| 5 | `narrator_mode` metadata field | Cheap provenance. Cleaner than parsing `narrative_model` strings. Enables quality comparison filtering. |
| 6 | API mode uses curated pipeline, not per-turn | Per-turn = 500 API calls ($15-25). Curated = 10-20 calls ($0.15-0.30). Local inference is free so per-turn is fine; API should be selective. |
| 7 | Post-loop narration before bridge close | Preserves option to thread agent context in future. M44 matches `_run_narrate()` agent context level (limited). |
| 8 | ERA_REGISTER experiment is pre-M44 | Prompt design decision should be data-driven before implementation, not discovered after. Four conditions (Claude/local x full/light) give a complete decision matrix. |
| 9 | Quality comparison uses `_run_narrate()` for both | Same pipeline, same prompts, isolated model variable. `execute_run()` comparison is confounded (different prompt paths). |
| 10 | `--narrator api` + `--live` is validation error | API latency incompatible with WebSocket real-time feed. |
| 11 | Curated entries replace per-turn empty entries | In API mode, the noop lambda produces `narrative=""` per turn. Curated `narrate_batch()` output replaces this list before `assemble_bundle()`. Empty entries have no value. (Phoebe B-1) |
| 12 | Validation above `_run_narrate()` early return | The `--narrate` path early-returns before the general validation block. API checks must precede it to avoid stack traces instead of clean messages. (Phoebe NB-1) |
| 13 | `--narrator api` + `--batch --parallel` is validation error | Parallel workers can't share `AnthropicClient` or token tracking. Per-worker token counts lost on process exit. (Phoebe NB-2) |
