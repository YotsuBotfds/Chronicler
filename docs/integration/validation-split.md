# Validation split (2026-11)

Branch `pass2/validation-split` from `fb25429` (`cleanup/streamline-pass-2-20261104`,
stacked on PR #71). Validation tooling only: no simulation, bundle, sidecar,
threshold or report change. This note records how the validation modules fit
together before the split, the parity tests that pin them, and each stage.

## 1. Characterization at `fb25429`

`validation_io.py` (4,631 lines) holds batch admission, bundle and sidecar
loading, every oracle algorithm, an orchestration `run_oracles` and a CLI.
`validation_oracles.py` (33 lines) re-exports 20 oracle names from it.
`validate.py` (187 lines) re-exports both modules (`__all__`: 100 entries) and
defines a second `run_oracles` and CLI. `validation_gate`, `validation_compare`,
`validation_ablation` and `validation_communities` are separate modules;
`validation_gate` and `validation_compare` name `chronicler.validate` only in
docstrings.

### Entry points

| Entry point | Defined | Used by |
| --- | --- | --- |
| `python -m chronicler.validate` | `validate.py` `__main__` guard | `scripts/m53b_run_validation.py` (`run_validation`, a child process: `--batch-dir B --oracles all --profile P [--ablation-dir D] [--require-causal-oracles \| --no-require-causal-oracles]`), which the Validation Gate workflow runs; `tests/test_m53b_run_validation.py` runs `--help` |
| `python -m chronicler.validation_io` | `validation_io.py` `__main__` guard (placed before `__all__`) | nothing in the repository |
| `validate.main(argv)`, `validation_io.main(argv)` | in process | tests only |
| console scripts | `pyproject.toml` has only `chronicler = chronicler.main:main` | none for validation |

### Callers and import sites

- `src/`: `agent_bridge.py` imports `detect_communities` from
  `chronicler.validate`; `validation_ablation.py` imports
  `_needs_snapshot_from_columns`, `_graph_snapshot_from_columns` and
  `detect_communities` from `validation_io` inside functions;
  `validation_communities.py` imports `_sample_turns` and `required_seed_count`
  from it inside a function; `validation_oracles.py` and `validate.py`
  re-export it.
- `scripts/`: `m53b_run_validation.py` (the CLI, above). Archived scripts:
  `m53_oracle_probe.py` (six oracle helpers from `chronicler.validate`),
  `rescore_cohort_oracle.py` (`load_seed_runs`, `_load_agent_events`,
  `_load_agent_deaths`, `_read_arrow_columns`, `_total_turns`,
  `run_cohort_oracle`, `BUNDLE_FILENAME`,
  `COHORT_ABLATION_DESIGN1_METHOD_VERSION` from `validation_io`),
  `benchmark_validation_turn_index.py` (`_read_arrow_columns`,
  `_available_turns_from_columns`, `_columns_for_turn`, `run_oracles`; it also
  hashes the `validation_io.py` of its `--source` tree),
  `benchmark_lean_ablation.py` (`load_seed_runs`) and
  `synth_ablation_oracles.py` (`EVENT_NAME_TO_CODE`).
- `tests/`: 17 modules. `test_validate.py` uses 24 names through
  `chronicler.validate` and 21 through `validation_io`; the others import
  `run_oracles`, `main`, `load_seed_runs`, `check_batch_manifest`, the event
  loaders, the column/snapshot helpers, the oracle runners and method
  constants, and `ORACLE_RUNNERS`. Every one is in the pinned import surface
  (section 2).
- Workflows: `validation-gate.yml` runs `scripts/m53b_run_validation.py` and
  imports `chronicler.validation_gate.load_validation_report`.

### Monkeypatch sites

| Target | Where | Reaches |
| --- | --- | --- |
| `validation_io._load_bundle` | `test_batch_manifest_reconciliation.py` (`_track_loader`) | both `run_oracles` (`iter_bundles`, `run_determinism_gate`) |
| `validation_io._read_arrow_columns` | `test_batch_manifest.py` | both (`load_seed_runs`) |
| `"chronicler.validation_io._has_pyarrow"`, `V._has_pyarrow` | `test_validate.py` (3), `test_validation_shared_event_table.py` | both, and both CLIs |
| `"chronicler.validation_io._load_agent_events"` | `test_validate.py` | nothing: no production path calls it (`load_seed_runs` reads `_load_agent_events_and_deaths`); the `validation_oracles` docstring's claim that the split keeps this target effective is stale |
| `V._world_shape` | `test_validation_shared_event_table.py` | `load_seed_runs` |
| `V._build_turn_rows` | `test_validation_turn_index.py` | `_IndexedColumns`; the test forbids calls, so moving the class away from this lookup would make it pass vacuously |
| `validation_io._filter_events_window`, `compute_cohort_distinctiveness` | `test_validate.py` | the cohort oracle (`_cohort_observational`) |
| `validation_io.run_needs_oracle`, `run_arc_oracle` | `test_validate.py`, `test_batch_manifest_reconciliation.py` | `validation_io.run_oracles`; see re-entry below |
| `validation_io.load_seed_runs`, `validate.load_seed_runs` | `test_validate.py` (parametrized) | that module's `run_oracles` only |
| `validate.ORACLE_RUNNERS[...]` (`setitem`) | `test_validate.py`, `test_batch_manifest_reconciliation.py` | `validate.run_oracles` only |
| `validate.run_oracles`, `validation_io.run_oracles` | `test_validate.py` | that module's `main` only |

**Re-entry.** `run_community_oracle` (method 2 re-scores method 1),
`run_needs_oracle` (methods 7 and 8 compute method 6) and `run_cohort_oracle`
(methods 4 and 5 compute method 3; the current method 6 does not) call
themselves through the module-level name. So a patch of
`validation_io.run_community_oracle` or `run_needs_oracle` also changes what
`validate.run_oracles` reports, although its registry holds the original
functions. These runners must stay where that name is looked up.

### The two `run_oracles`

Both have the signature `(batch_dir, oracles, profile=None, *,
legacy_batch=False, ablation_dir=None, require_causal=None)` and the same
algorithm: resolve `require_causal` (`causal_oracles_required`), normalize the
selection, admit the batch (`_prepare_batch_admission`), load the ablation arms
(`_load_arms`), load seed runs once on first use, run the selected oracles in
sorted order (`ValidationRequestError` and `ValidationDependencyError`
propagate; any other exception becomes `{"status": "ERROR", "reason": "Type:
message"}`), then build the report with the keys `batch_dir`, `oracles`,
`results`, `worlds` (non-template batches only), `batch_manifest`,
`ablation_arms` (with arms), `profile` (when given) and
`causal_oracles_required`. Their docstrings differ only in a reference to
`validation_ablation.load_ablation_arms`. On every synthetic scenario of the
parity tests their unpatched reports are byte-identical. They differ in how
they find their collaborators, which tests rely on:

| | `validate.run_oracles` | `validation_io.run_oracles` |
| --- | --- | --- |
| Oracle dispatch | the `ORACLE_RUNNERS` dict, filled at import with `validation_io`'s functions; looked up before each oracle's `try` | each `run_*` function by its module-level name at call time, inside the `try` |
| Allowed names, `all` | the registry's current keys (a test can add or delete one) | the fixed `ORACLE_RUNNER_NAMES` |
| Seed-run oracles | `SEED_RUN_ORACLES` (fixed at import) | `SEED_RUN_ORACLE_NAMES` (the same seven names) |
| Determinism | with `_admission` when the registry entry is `validate.run_determinism_gate`; otherwise `admission.finish()` and then `runner(batch_dir)`, the standalone signature (8 against 12 bundle reads on the parity batch) | always `run_determinism_gate(batch_dir, _admission=...)`, also for a replacement |
| Other collaborators | `validate`'s module attributes: `load_seed_runs`, `_prepare_batch_admission`, `_load_arms`, `ablation_methods`, `summarize_world_shapes`, `causal_oracles_required`, `_normalize_requested_oracles` | the same names in `validation_io` |

`validate`'s module attributes `run_needs_oracle` and the other runners are
not its registry: patching them changes nothing, except that a patched
`validate.run_determinism_gate` selects the standalone call above.

### The two CLIs

Both build the same parser (description `M53b validation oracle runner`):
`--batch-dir` (required), `--oracles` (one or more, default `all`),
`--profile` (`subset`, `full`, `determinism-off`, `determinism-hybrid`;
default none), `--legacy-batch`, `--ablation-dir` and
`--require-causal-oracles` / `--no-require-causal-oracles` (default none).
Both write the report as strict JSON (`strict_json_dumps`: indent 2, ASCII,
trailing newline) to stdout and nothing to stderr. A request or dependency
error writes `{"batch_dir", "oracles", "results": {}, "status": "ERROR",
"reason"}` and exits 1; so does a report that cannot be written as strict
JSON (NaN or infinity, non-string keys), with the reason `could not serialize
validation report: ...`; any oracle result with status `ERROR` exits 1;
otherwise 0. argparse exits 2 on a usage error and 0 after `--help`. Each
`main` calls its own module's `run_oracles`, `_dump_report`, `_error_report`
and `_serialization_error_report`.

The only output difference is the `--require-causal-oracles` help:
`validate` says the ablation components are "needs method 8, cohort method
5", `validation_io` "needs method 7, cohort method 4". Design-2 arms are
scored by needs method 8 and cohort method 6 (5 with the legacy
communities), design-1 arms by methods 7 and 4, so neither text is wholly
current. Each surface keeps its own text; it is not corrected here.

A ledger entry of 2026-10-07 (`docs/superpowers/progress/phase-6-progress.md`)
reviewed the CLI duplicate and kept it, because the bodies preserve distinct
module-local callbacks and `python -m` entry points.

### Pins

- No validation module is listed in a source witness: the 12
  `tests/fixtures/*_source_inverse.json` files pin 80 paths through `files`
  and `new_files`, among them `src/chronicler/batch_manifest.py` (not
  touched here) and none of `validate.py` or `validation_*.py`.
- `tests/fixtures/performance/corrected_*.json` record historical SHA-256s of
  these files (`validate.py` `304fe17c...`; it is now `a895b720...`, and the
  tests pass), so they are provenance, not checks.
  `tests/fixtures/reference_baselines/26e1869.../MANIFEST.json` verifies its
  own stored copies, not the current source.
- No test reads these modules' source text, line numbers or hashes, or
  inspects their functions' source. `batch_manifest.package_digest` hashes
  every package file when a batch runs, so new modules change future
  digests as any source change does.
