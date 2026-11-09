# API narrator budgets (2026-11)

Code: `src/chronicler/llm.py` (`_UsageBudget`, `AnthropicClient`,
`GeminiClient`, `create_clients`), `src/chronicler/narrative.py`
(`_narrate_batch_api`). Tests: `tests/test_llm.py` (`TestClientSafeguards`,
`TestBatchBudget`), `tests/test_narrative.py`. Narration only; the simulation
is unchanged.

`create_clients(..., max_total_tokens=None, max_calls=None)` passes both
limits to the API narrators (`--narrator api` and `--narrator gemini`). The
default `None` means unlimited. There is no CLI flag.

## One policy for every submission path

`AnthropicClient` and `GeminiClient` share one budget (`_UsageBudget`) and one
set of counters (`total_input_tokens`, `total_output_tokens`, `call_count`).
Sequential `complete()` calls and Anthropic `batch_complete()` draw on the same
budget, in either order.

- **Exhausted budget.** When the token threshold or the call limit has been
  reached, `complete()` and `batch_complete()` raise `LLMBudgetExceeded`
  before any SDK call (`messages.create`, `messages.batches.create`,
  `models.generate_content`).
- **Call limit.** `max_calls` counts completions with a successful response.
  A batch submits at most `max_calls - call_count` requests: the first ones in
  order. The rest are not sent, come back as `None`, and one warning is
  logged.
- **Token threshold.** `max_total_tokens` is checked at admission, before each
  call or batch is submitted. Usage is counted from the responses. It is a
  threshold, not a hard spending ceiling: a call or batch admitted under it
  can overshoot it by its own usage (a whole batch can, since its usage is
  only known from its results).

## What the narrator does

On the sequential path (local, Gemini) each refused `complete()` call falls
back to the moment's mechanical text, with one warning and a final count.
The batch path matches it: the moments inside the remaining call allowance
are narrated, the later ones (a `None` result) are rendered mechanically, and
an `LLMBudgetExceeded` raised before submission renders every moment
mechanically with one warning instead of stopping the run.

`GeminiClient` has no batch path; every request goes through `complete()`.
