# Detached four-kernel governance experiment

This branch provides a usable opt-in experiment on public base
`edf72991cad58d6670b1f382c33d50d903a6054a`. Inputs must be explicit synthetic
fixtures. Nothing is wired into the production runtime, shared models, simulation,
agent bridge, native pool, or normal CLI. G05 is permission-blocked: its source was
not accessed, reconstructed, or substituted. There is no PSI computation.

Run the complete example from the checkout root:

```sh
PYTHONPATH=src python examples/governance_four_kernel.py
```

It creates an explicit policy, starts a synthetic reign, saves and reloads exact
carry, then funds an enactment and a mock suppression from one 0.30 wallet. It
prints effective turn 2, both approved actions, exact capital `[0,1]`, legitimacy
0.6, and one keyed ambition contribution. These numbers are illustrative fixtures.
Mock suppression acknowledges a supplied synthetic intent; it prevents no actual
simulation secession. No RNG stream is consumed; explicit independent draws are
provided only on accession and inside proposal attempts.

Use `run_kernel_frame(opening=..., enabled=True, observations=..., policy=...)`.
The default `enabled=False` returns the identical opening carry without reading
inputs, calling kernels, or consuming draws. Enabled use requires a complete
`HarnessPolicy` and a source-stamped `SyntheticFrame`. The integer identity
registry is persistent; G04 civ and trade-partner IDs use canonical decimal strings.
Observations must contain every registered civilization, with one ownership epoch
and fresh source turn. G02 population is explicitly the supplied synthetic living
row count. Absent-backed GP wealth/satisfaction must be supplied explicitly; no
agent, population, wealth, age, settlement or fiscal extractor is implemented.

## Transaction and persistence

Policy `synthetic-enact-repeal-mock-suppress-v1` chooses enactments, forced repeals,
then eligible mock suppression in stable subject order. Institution operations use
enum order and G01 `PROPOSE_THEN_REPEAL`. This reviewed experimental choice does
not establish historical calibration or production chronology.

G01 receives an opening-portfolio fiscal quote. Replays are pure structural probes
from the same frozen opening, never from an intermediate next portfolio. The G01
helper also revalidates its quote during probes; that is arithmetic, not repeated
payment. Only structurally acknowledged approvals retain tentative G03 debits.
Structurally eligible but unaffordable requests remain in the final complete batch;
unused attempts appear only in diagnostic request receipts. The complete ordered
G03 batch must reproduce every provisional decision and exact remainder, and final
G01 acknowledgements must form a bijection with institutional approvals. Later
repeals cannot enable earlier failed enactments. Late enactments first incur fiscal
demand next turn; repeal preserves current-turn demand. Final portfolio support
feeds G03 accrual; generated capital first becomes available next turn.

All calculations are immutable. A failure in any civilization publishes no result
and leaves the entire opening unchanged. `HarnessCarry.last_committed_turn` and
source epochs reject replay against committed carry. Recomputing an old immutable
opening is a pure preview; callers must atomically replace their stored carry with
the result. This library performs no database/file commit, lock, or external side
effect. `CivReceipt` exposes final funding, institution outcomes/events, spend
ledger, accrual breakdown, request diagnostics and ambition outcomes for inspection.

`carry_to_json` / `carry_from_json` use versioned tagged JSON with a closed type
registry. Every capital Fraction uses integer numerator/denominator pairs, retaining
residuals invisible in its float view. Duplicate JSON fields, unknown records,
inconsistent epochs, missing terminal contributions and inconsistent signs fail.
Signed ambition contributions use collision-free versioned five-component keys;
same-key/same-value merging is idempotent, contradictory values fail. The complete
retained contribution map enters each legitimacy recomputation; saturated previews
do not discard rewards. Contribution outcomes never become war victories.

On accession, the caller supplies a unique reign ID, succession kind, independent
draws and an accession event cursor within the observed frame. Remaining capital
is explicitly carried or reset to zero. Old goals and contributions are archived;
civ tags remain available. New objectives are evaluated starting with the following
frame. Post-accession evidence is persisted, including after save/load. A durable
per-civ evidence log prevents rewriting consumed sequences, and its unevaluated
suffix must match the pending queue. The required experimental
`monotone_complete_cursor_log` policy rejects previously unseen evidence at or below
an already observed cursor; delayed historical log insertion is unsupported.
Accession boundaries cannot precede the previously committed evidence cursor.

## Explicit policy choices and gates

No funding/rounding/timing policy is inferred. Unsupported or missing choices fail.
The one implemented experimental contract requires:

- Helper base-first full debit (including debt) or a matching explicit external
  aggregate funding record. Neither mode executes a treasury write. Fractional
  fiscal fixture amounts have no integer-treasury rounding rule.
- Persisted enactment prices and aggregate institutional erosion; annual repricing
  and per-institution payment allocation are unsupported.
- Explicit elite calibration and LOWER/UPPER percentile, FLOOR/CEIL office count,
  and equal-wealth ranking conventions; no absent-GP imputation.
- Reign-long signed ambition retention without decay, deferred accession evaluation,
  explicit carry/reset succession capital, and abort-on-missing observations.
- An explicit Fraction capital bound. Exceeding it aborts; no implicit clamp,
  saturation, rounding tolerance or overdraft is introduced. This is an experimental
  validation bound, not a roadmap production-cap rule.

G04's source originally sorted types lexically. The actual baseline roadmap's
Determinism Guardrails (line 1102) require enum-index candidates before selection,
and its enum is defined at lines 758–763. The authorized minimal fix orders weights,
reign objectives and generated output by that enum index. A fixed draw gives the
first, longer deadline to CONQUER_REGION rather than lexical BUILD_MONUMENT.
Original source commits remain listed in `provenance.json`, including G04's two
commits; the integration uses scoped cherry-picks and a separately reviewable fix.

Production remains gated on cross-phase scheduling/reservations; fiscal allocation,
integer rounding/carry/repricing and denominator epochs; elite/GP conventions and
calibration; accession/contribution policies; dedicated RNG reservation; recent tag
aging; verified G05 delivery and explicit authorization; and applicable public M61,
M64/M65a, PSI/M67 and M61b acceptance. Joint synthetic tests satisfy none of these
activation gates. No GitHub writes or sharing changes were made.

## Verification

The supplied contract, four source archives and historical archive were fetched
through connected Drive, then fully materialized. Exact outer byte counts/hashes,
safe relative member paths, all member hashes and exact member sets were checked
before use. Bundles were verified locally; imported changes were restricted to the
four module/test pairs and their expected public-base ancestry. Checkout `.agents`
and `.codex` directories were empty; no AGENTS.md or relevant local skills existed.
Historical intent was read as evidence, not applied as a runtime change.

Constituent suites and joint tests:

```sh
python -m pytest -q tests/test_institutions.py tests/test_elite_metrics.py \
  tests/test_governance_capital.py tests/test_ruler_ambitions.py \
  tests/test_governance_kernel_harness.py
```

Relevant unchanged-runtime regression selection, run both on public base and final
HEAD, with native/slow tests excluded:

```sh
python -m pytest -q -m 'not slow and not native' tests/test_models.py \
  tests/test_factions.py tests/test_dynasties.py tests/test_politics.py \
  tests/test_simulation.py tests/test_agents_off_determinism.py \
  tests/test_validation_population.py tests/test_bundle.py
```

The environment uses Python 3.13.5. The supplied lockfile does not satisfy
`uv sync --locked` under this checkout's existing project metadata. Dependencies
were installed from the lockfile with `uv sync --frozen`, with explicitly required
NumPy/SciPy/PyArrow/arro3 packages added only to the isolated test environment.
Repository metadata and lockfiles were unchanged. Native validation is outside
this task; available regression skips are reported, never counted as passes.
Final HEAD evidence and independent Sol findings/dispositions accompany the handoff.
