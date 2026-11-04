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
| `"chronicler.validation_io._load_agent_events"` | `test_validate.py` | nothing: no production path calls it (`load_seed_runs` reads `_load_agent_events_and_deaths`); the `validation_oracles` docstring's claim that the split keeps this target effective was stale (corrected in section 4) |
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

## 2. Parity tests

`tests/test_validation_parity.py` (shard 0, the `validation-tooling` chunk of
`scripts/run_python_oracle_checks.py`) builds small deterministic batches in
the test: three 160-turn seeds with every sidecar and a verified manifest,
design-1 and design-2 ablation arms for them, a determinism batch with a
matching and a differing pair, a legacy procedural batch, a batch whose
needs table lacks columns (an `ERROR` result) and one whose summary holds
NaN. Its goldens (`tests/fixtures/validation_parity/goldens.json`) were
generated from `fb25429`; paths and input digests are replaced by labels so
they hold on any platform and pyarrow version. It pins:

- each surface's report text for 9 scenarios, its CLI stdout, stderr and exit
  status for the same scenarios, 5 request errors (message and CLI error
  report), the unserializable report, and argparse's help, usage and
  invalid-choice output (whitespace collapsed);
- the import surface: the three `__all__` lists, every name `validation_io`
  binds with its kind (211), the values of its 72 constants, and the identity
  of every re-export;
- which monkeypatch reaches which surface: seven `validation_io` helpers with
  their call counts, each orchestration and CLI collaborator per surface, the
  module-function and registry dispatch including the re-entry above, the
  determinism standalone call, and registry entries added and removed.

## 3. One orchestration and one CLI

Neither public `run_oracles` can simply call the other: `validate`'s would
then see patches of `validation_io.run_*` (and its `load_seed_runs`), or
`validation_io`'s would see `validate.ORACLE_RUNNERS`. So the canonical path
is one private engine, `validation_io._run_oracles`, and both public
functions are one-statement wrappers that keep their signatures, defaults and
docstrings:

- The engine is `validate`'s registry algorithm, the general form: it takes
  the calling module (`surface`), a registry and the seed-run oracles, and
  reads `causal_oracles_required`, `_normalize_requested_oracles`,
  `_prepare_batch_admission`, `_load_arms`, `load_seed_runs`,
  `ablation_methods`, `summarize_world_shapes` and `run_determinism_gate`
  from `surface` when it uses them. The determinism standalone call is
  kept: it applies when the registry entry is not
  `surface.run_determinism_gate`.
- `validate.run_oracles` passes its module, `ORACLE_RUNNERS` and
  `SEED_RUN_ORACLES`. It is the production path (`python -m
  chronicler.validate`, run by the gate runner).
- `validation_io.run_oracles` passes its module, `_ModuleRunners` (its
  `run_*` functions as a registry, read from the module when each oracle
  runs) and `SEED_RUN_ORACLE_NAMES`. Its determinism entry is always its
  own `run_determinism_gate`, so it always shares the admission, as before.
- `_normalize_oracle_selection(oracles, names)` is the one normalization;
  each module's `_normalize_requested_oracles` passes its names (the live
  registry keys, or `ORACLE_RUNNER_NAMES`).
- `validation_io._cli_main(surface, argv, causal_help=...)` is the one CLI.
  Both `main` functions pass their module and their own
  `--require-causal-oracles` help (`_CAUSAL_ORACLES_HELP`), so each CLI's
  output stays byte for byte as pinned, the method 8/5 against 7/4
  mismatch included. `validate` imports `_error_report`, `_dump_report` and
  `_serialization_error_report` instead of defining copies; each `main`
  still reads them, and `run_oracles`, from its own module.

The parity tests pass unchanged on `fb25429` and after this stage, except
one assertion: the report helpers are now shared objects, so the identity
check that each module owns a distinct copy is limited to `run_oracles`,
`main` and `_normalize_requested_oracles` (the per-module lookup of the
helpers is pinned separately and unchanged). Both `python -m` entry points
give the pinned output as child processes, on `fb25429` and here (28 runs
each, run outside pytest because the bounded lane's offline guard forbids
child processes).

Two differences remain, both under patches no test or script makes:

- `validation_io` used to look up a runner inside each oracle's `try`, so
  deleting `validation_io.run_era_oracle` (`monkeypatch.delattr`) gave that
  oracle an `ERROR` result; the engine looks runners up before the `try`, as
  `validate` always did, so the `AttributeError` now propagates.
- `validate.main` used to build its parser from `validate`'s own bindings of
  the flag names and profile choices, catch `validate`'s bindings of the
  exception classes and serialize with `validate`'s `strict_json_dumps`; they
  are the same objects as `validation_io`'s, which the shared CLI now uses,
  so rebinding one of them on `validate` alone no longer changes its CLI.

`validate.py` is 85 lines (187 before), `validation_io.py` 4,707 (4,631).
pyflakes ignores `# noqa`: it now reports the explicit re-exports of
`validate.py` (which the engine reads as module attributes, so they stay
patchable) and `validation_io`'s module-level `causal_oracles_required` as
unused; there are no other new findings.

## 4. Extraction

Four modules now hold definitions moved verbatim out of `validation_io`, one
commit each. `validation_io` re-exports every moved name (the same
objects), so every import path, the three `__all__` lists, `validate`'s and
`validation_oracles`' re-exports and `ORACLE_RUNNERS` are unchanged.

| Module | Lines | Holds |
| --- | --- | --- |
| `validation_common.py` | 31 | `EVENT_NAME_TO_CODE`, `required_seed_count`, `_mean`; a leaf that imports no validation module, so the others share them without an import cycle |
| `validation_artifacts.py` | 187 | the artifact oracle: the `ARTIFACT_*` thresholds, `check_artifact_lifecycle`, `run_artifact_oracle` (8 names) |
| `validation_trajectories.py` | 721 | the era and arc oracles, which share their series helpers: the `ERA_*` thresholds, `detect_inflection_points`, `detect_collapse_episodes`, `run_era_oracle`, the arc classifiers, `run_arc_oracle` (20 names) |
| `validation_regression.py` | 789 | the regression summary: the `REGRESSION_*` floors, `run_regression_summary` and its helpers (23 names) |

`validation_io.py` went from 4,631 to 3,063 lines, `validate.py` from 187
to 85; `validation_oracles.py` is 38 (a corrected docstring).

**What may move.** A family moves only with its whole dependency closure
(computed from the AST), when no definition in it reads as a global a name
that tests patch through `validation_io`, and when the closure needs nothing
from `validation_io` but `validation_common` and the standard library.
`test_functions_reading_patched_names_stay_in_validation_io` enforces the
first rule for every validation module, so a later move that would silently
detach a patch fails.

**How each move was checked**, by script against `fb25429`: every moved
definition (54) has the baseline's AST and source text; every global a moved
function reads (188) resolves in its new module to the object
`validation_io` binds; the parity goldens, the import-surface pins, the
placement guard and the focused validation suites pass.
`python tests/test_validation_parity.py` regenerates the behaviour goldens
from the current tree and compares them with the fixture (`--write`
rewrites them; the import-surface pins are kept as committed): they match
both `fb25429` and the split tree byte for byte. The module docstrings of
`validation_io` and `validation_oracles` now describe where each oracle
lives.

**What stays in `validation_io`, and why.**

- Batch admission and bundle and sidecar loading: tests patch
  `_load_bundle`, `_read_arrow_columns`, `_has_pyarrow`, `_world_shape` and
  `_build_turn_rows` here, and the loaders are their callers.
- The needs, cohort and community oracles with their helpers and ablation
  method results: the runners re-enter through their module-level names, and
  the cohort and best-of paths call the patched `_filter_events_window` and
  `compute_cohort_distinctiveness`. Their pure helpers (pair matching,
  concordance statistics, `detect_communities`) could move alone, but each
  family would then be split across two modules.
- `run_determinism_gate`, which calls the patched `_load_bundle`.
- The crisis event types (`ERA_CRISIS_*`), read by the loader.
- `_run_oracles`, `_cli_main` and the report helpers: they catch
  `validation_io`'s exception classes and build the parser from its flags, so
  moving them would need imports inside the functions (changed bodies, not a
  verbatim move) or moving the exception classes (whose `__module__` would
  change). Not done.

**pyflakes.** The new modules have no findings. In `validation_io`, the new
findings are the re-export imports of moved names that are not in its
`__all__` (marked `# noqa: F401`, which pyflakes ignores) and `math.ceil`,
kept because every name `validation_io` bound before the split stays bound;
`validate.py`'s are its explicit re-exports (section 3). The baseline's
findings remain: `verify_batch_manifest` (an unused import), the
`pyarrow.ipc` probe and `validate.py`'s star imports.

**Risks.** Code outside the repository that patches a moved name through
`validation_io` (say `validation_io.classify_civ_arc`) and expects
`run_arc_oracle` to see the patch no longer reaches it; no test or script
does, and the guard covers every name patched today. Moved functions report
their new `__module__`. `scripts/archive/benchmark_validation_turn_index.py`
hashes the `validation_io.py` of its source tree, which now covers less of
the validator. Batch manifests' package digests change, as with any source
change.
