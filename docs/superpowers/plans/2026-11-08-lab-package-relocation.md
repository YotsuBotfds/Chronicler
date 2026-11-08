# `chronicler_lab` Package Relocation — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** move the 29 modules unreachable from production into `src/chronicler_lab/`, keeping old import paths alive through shims, in seven independently green PRs.
**Architecture:** sibling package, one-way dependency `chronicler_lab -> chronicler`; `git mv` module, rewrite its internal imports, rewrite every in-repo importer, leave a shim (alias via `sys.modules`); tests and scripts stay where they are.
**Tech stack:** Python 3.13, hatchling, pytest, `scripts/refactor_preflight.py`.
**Prerequisites:** DEC-6 answered (move; package name; sub-decision A: whether `validation_compare` and `community_admissibility` stay; shim lifetime). Work from fetched `main`. Spec: `specs/2026-11-08-lab-package-relocation-design.md`. If DEC-6 picks another name, substitute it everywhere below.

## Common recipe (used by PRs 2 to 6)
Let `MODS` be the PR's module list.
- [ ] R1 Preflight, read-only: `for m in $MODS; do .venv/bin/python scripts/refactor_preflight.py --move src/chronicler/$m.py:src/chronicler_lab/$m.py; done`. Expect no `enforced` lines; `digest` lines only for the modules named in spec section 5. Read each `string target` and `test names path` hit.
- [ ] R2 `git mv src/chronicler/$m.py src/chronicler_lab/$m.py` (history kept).
- [ ] R3 Fix imports inside each moved file: relative `from . import X as y` / `from .X import ...` become `from chronicler import X as y` / `from chronicler.X import ...`; imports of other lab modules become `from chronicler_lab import Y`. No other edit. Check with `rg -n "^\s*from \.|chronicler import (<all 29 names>)" src/chronicler_lab/$m.py` (expect none for the second pattern except lab names already rewritten).
- [ ] R4 Create the shim `src/chronicler/$m.py` (template in spec 3.3; add the `__main__` branch only for the 7 CLI modules). Append `$m` to `src/chronicler_lab/SHIMS`.
- [ ] R5 Rewrite in-repo importers (scripts, tests, other lab modules) to the new path. Use this one-off, not committed:
  `.venv/bin/python - <<'PY'` that walks `scripts/ tests/ src/chronicler_lab/ docs/ README.md` (skip `tests/fixtures/`, `docs/superpowers/audits|progress`, `docs/**/*.json|log|jsonl`) and applies `re.sub(r"\bchronicler\.(MODS)\b", r"chronicler_lab.\1", s)` and for `from chronicler import a, b` splits the lab names into `from chronicler_lab import ...`. Then `git diff --stat` and read it.
  Do not touch `tests/fixtures/reference_baselines/**` (frozen copies; hashes are verified by `tests/reference_baselines.py:7-14`).
- [ ] R6 Repoint the path pins and closure assertions listed for the PR (spec section 5), including string monkeypatch targets, so shim removal is later a no-op.
- [ ] R7 Verify: (a) the PR's focused test files; (b) `.venv/bin/python -m pytest -q tests/test_import_compatibility.py tests/test_native_ci_shards.py tests/test_script_smoke_manifest.py`; (c) `.venv/bin/python scripts/run_python_oracle_checks.py` (every chunk passes, none near 110 s); (d) `.venv/bin/python scripts/turn_speed_identity.py run` on the PR and on `main`, then `compare`: identical (production files unchanged). Never run with the native extension in the oracle lane.
- [ ] R8 Docs: update the doc files that name the module (`rg -l "chronicler[./]<m>" docs README.md`), `scripts/testing/script_smoke_manifest.json` note text if it names the module. Add the CONTINUATION paragraph (structural move, no behaviour change, no baseline). Commit message: `Move <cluster> harnesses to chronicler_lab (no behaviour change)`.

## File map
| File | Change |
|---|---|
| `src/chronicler_lab/__init__.py`, `SHIMS` | new (PR 1); `SHIMS` lists shim module names, deleted in PR 7 |
| `pyproject.toml` | hatch `packages` table (PR 1) |
| `src/chronicler/<29>.py` | become shims (PRs 2-6), deleted (PR 7) |
| `src/chronicler_lab/<29>.py` | `git mv` targets |
| `tests/test_import_compatibility.py` | boundary guard, shim identity, CLI shim smoke, checkpoint identity test |
| ~50 files under `tests/`, 21 under `scripts/` | import and path edits only |
| `README.md:220`, `docs/DEVELOPMENT.md`, `AGENTS.md`, ~30 docs | module path text |
| `tests/test_native_build_lanes.py:86` | only if `validation_compare` moves (PR 6) |
| Not touched | `scripts/testing/native_shards_manifest.json`, `scripts/run_python_oracle_checks.py`, `.github/workflows/*`, `docs/workflows/*.yml.in`, `tests/fixtures/**` |

## PR 1: Scaffold and guards (no module moves)
### Task LAB-1a: package, packaging, boundary tests
- [ ] Step 1: Create `src/chronicler_lab/__init__.py` containing only a docstring ("Detached harnesses; production never imports this package; see docs/DEVELOPMENT.md"). Create `src/chronicler_lab/SHIMS` (empty text file; one module name per line).
- [ ] Step 2: In `pyproject.toml`, after `[build-system]` (`:32-34`), add `[tool.hatch.build.targets.wheel]` with `packages = ["src/chronicler", "src/chronicler_lab"]`. Run `uv lock --check`; expect success.
- [ ] Step 3: In `tests/test_import_compatibility.py` add:
  - `test_production_never_imports_chronicler_lab`: AST-scan every `src/chronicler/**/*.py` except names in `SHIMS`; assert no `chronicler_lab` import and no string constant equal to a name in `SHIMS` or in the 29-name tuple `LAB_MODULES` (declare the tuple in the test).
  - `test_lab_modules_not_reachable_from_roots`: port `docs/superpowers/plans/2026-11-08-tools/lab_reachability.py` (roots `main`, `live`, `validate`, `narration_audit`; treat `import_module("chronicler." + x)` sites as reaching the livelihoods names `learning_cohorts`, `remittances`, `timber_orders`, `wealth_accounting`); assert the reached set excludes `LAB_MODULES`. Before any move the check fails for modules not yet moved, so write it `xfail`-free: assert only for names currently present under `src/chronicler_lab/`.
  - `test_shims_are_identity_aliases`: for each name in `SHIMS`, `importlib.import_module("chronicler."+n) is importlib.import_module("chronicler_lab."+n)`.
  - `test_cli_shims_run_as_module`: for the CLI names present in `SHIMS` run `sys.executable -m chronicler.<n> --help` with `PYTHONPATH=src`, expect the same stdout as `-m chronicler_lab.<n> --help`.
- [ ] Step 4: `docs/DEVELOPMENT.md`: add a "Detached lab package" subsection (rule: production must not import `chronicler_lab`; receipts' source identity covers `src/chronicler` only). `AGENTS.md` architecture list: add one bullet for `src/chronicler_lab/`.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest -q tests/test_import_compatibility.py` passes; `.venv/bin/python scripts/run_python_oracle_checks.py` passes. Build check: `uv build --wheel` into a temp dir (not the repo) and confirm `chronicler_lab/__init__.py` is listed in the wheel.
- [ ] Step 6: Ledger: CONTINUATION paragraph; commit `Add chronicler_lab package scaffold and import-boundary guards`.

## PR 2: Sessions and receipts (9 modules, 3,884 lines)
`experiment_sessions, memome_experiment, session_operations, session_comparison, experiment_receipt_inspector, memome_candidate_preview, campaign_order_preview, campaign_snapshot_adapter, snapshot_campaign_sessions`
### Task LAB-1b
- [ ] Step 1: Run R1-R5. Scripts to rewrite: `experiment_session.py, experiment_receipts.py, session_operation.py, compare_experiment_sessions.py, campaign_order_preview.py, memome_candidate_preview.py, memome_demo.py, campaign_snapshot_plan.py, snapshot_campaign_session.py, verify_snapshot_session.py`.
- [ ] Step 2 (R6 pins): `tests/test_experiment_default_boundaries.py:20` (path becomes `src/chronicler_lab/experiment_sessions.py`; `es.__file__` now resolves there even through the shim); `tests/test_snapshot_campaign_sessions.py:347,350,359` (path, `node.module == "chronicler_lab.campaign_snapshot_adapter"`, consumer set `{"src/chronicler_lab/snapshot_campaign_sessions.py"}` scanning `src/chronicler_lab` plus asserting `src/chronicler` has only the shim); `tests/test_snapshot_input_boundaries.py:396` (current path moves, the `baseline_source(PARENT, name)` key stays `src/chronicler/snapshot_campaign_sessions.py`: split the variable into `baseline_name` and `current_name`); `tests/test_campaign_snapshot_adapter.py:1045,1176,1191,1218,1230` (same consumer-scan treatment; `registry` read of `main.py` unchanged); `tests/test_reviewed_base_submission.py:31` (`OWNED` path); `tests/test_memome_candidate_preview.py:28`, `tests/test_campaign_order_preview.py:27`, `tests/test_memome_experiment.py:251`, `tests/test_experiment_sessions.py:31`, `tests/test_experiment_receipt_inspector.py:350-351`, `tests/test_session_comparison.py:440-449`.
- [ ] Step 3: Add to `tests/test_experiment_sessions.py` a test that `load_session` reads a pre-move session fixture: take any existing session fixture the file already builds (or write one with the old API through the shim, import `chronicler.experiment_sessions as old` and `chronicler_lab.experiment_sessions as new`), assert both loaders return equal `LoadedSession` state and that `old.load_session is new.load_session`.
- [ ] Step 4: Verify (R7) with: `.venv/bin/python -m pytest -q tests/test_experiment_sessions.py tests/test_experiment_default_boundaries.py tests/test_session_operations.py tests/test_session_comparison.py tests/test_session_io_boundaries.py tests/test_session_read_bounds.py tests/test_snapshot_campaign_sessions.py tests/test_snapshot_input_boundaries.py tests/test_snapshot_session_provenance.py tests/test_campaign_snapshot_adapter.py tests/test_campaign_order_preview.py tests/test_memome_experiment.py tests/test_memome_candidate_preview.py tests/test_experiment_receipt_inspector.py tests/test_experiment_workflow_integration.py tests/test_operator_submission_workflow.py tests/test_reviewed_base_submission.py tests/test_pd_input_boundaries.py`. Expect all pass; counts equal to `main`.
- [ ] Step 5: R8; commit.

## PR 3: Governance capture (3 modules, 1,948 lines)
`governance_measurements, governance_capture, governance_sequence`
### Task LAB-1c
- [ ] Step 1: R1-R5. R3 is essential: `governance_measurements.py:48-52` (`elite_metrics, governance_capital, governance_kernel_harness, institutions, ruler_ambitions`), `governance_capture.py:10-11`, `governance_sequence.py:11-12` use relative imports. Scripts: `governance_capture_report.py, governance_measurement_report.py, governance_sequence_report.py`.
- [ ] Step 2 (R6): `tests/test_governance_sequence.py:504,516` (`sys.modules["chronicler."+name]` and the expected path become `chronicler_lab`), `tests/test_governance_measurements.py:1069,1084` (import closure set and source path), `tests/test_governance_capture.py:21,315,407`, `tests/test_governance_example_isolation.py:18`. Leave `tests/test_governance_dormancy.py` and `tests/test_governance_kernel_harness.py` alone (production harness stays).
- [ ] Step 3: Verify: `.venv/bin/python -m pytest -q tests/test_governance_measurements.py tests/test_governance_capture.py tests/test_governance_sequence.py tests/test_governance_example_isolation.py tests/test_governance_dormancy.py tests/test_governance_kernel_harness.py`; then R7 (b)-(d).
- [ ] Step 4: R8; commit.

## PR 4: Expansion and science audits (6 modules, 3,451 lines)
`expansion_audit, expansion_compare, scientific_research_audit, scientific_receipts_audit, history_forensics, evidence_admission`
### Task LAB-1d
- [ ] Step 1: R1-R5. The `scripts/archive/audit_system_expansion.py` and `compare_system_expansion.py` import these; rewrite them too. CLI shims (all 4: `expansion_audit, expansion_compare, history_forensics, evidence_admission`). Docs: `docs/integration/history-forensics.md:15`, `docs/validation/evidence-admission.md:5`, `docs/integration/scientific-receipts-audit.md`.
- [ ] Step 2 (R6): none path-pinned; check `tests/test_historiography.py:576` and `tests/test_harvest_forecasts.py:853` (basename hits) by reading them.
- [ ] Step 3: Verify: `.venv/bin/python -m pytest -q tests/test_expansion_audit.py tests/test_expansion_compare.py tests/test_scientific_research_audit.py tests/test_scientific_receipts_audit.py tests/test_history_forensics.py tests/test_evidence_admission.py tests/test_historiography.py tests/test_harvest_forecasts.py`; then R7 (b)-(d).
- [ ] Step 4: R8; commit.

## PR 5: Health-care observation (4 modules, 2,253 lines)
`health_care_observation_codec, health_care_observation_mechanics, health_care_capture, artifact_budget`
### Task LAB-1e
- [ ] Step 1: R1-R5. `tests/test_health_care_policy.py:299` imports the codec at module scope and `:1019-1038` hashes `chronicler-agents/src/health_care_observation.rs` (Rust file: not moved, untouched). `tests/test_health_care_capture.py:600` closure set.
- [ ] Step 2: Verify: `.venv/bin/python -m pytest -q tests/test_health_care_policy.py tests/test_health_care_capture.py tests/test_health_care_experiment_policy.py tests/test_artifact_budget.py`; R7 (b)-(d). Native health-care tests are not part of this gate; do not claim them run.
- [ ] Step 3: R8; commit.

## PR 6: Miscellaneous (5 modules, 1,387 lines; 7 modules, 2,344 lines with sub-decision A)
`practice_growth, decision_delivery, kin_root_exposure, shadow_oracle, checkpoint_replay` plus, only if DEC-6 sub-decision A says move, `validation_compare, community_admissibility`.
### Task LAB-1f
- [ ] Step 1: R1-R5. Scripts: `capture_kin_root_exposure.py, a01_acceptance.py, run_oracle_gate.py`; `tests/kin_capture_driver_contract_cases.py` and `tests/kin_root_exposure_contract_cases.py` (helper modules, imported by chunk `scripts/run_python_oracle_checks.py:456`).
- [ ] Step 2: **checkpoint_replay identity fix.** In the moved file change line 144 to `package_digest(Path(chronicler.__file__).parent)` and add `import chronicler`. Update `tests/test_turn_artifact_runner.py:219-233`: it copies `replay.__file__` into a temp dir and patches `replay.__file__` so a new file changes the digest. After the fix the digest follows `chronicler.__file__`, so build the temp tree as a copy of the production `chronicler` package skeleton (`__init__.py` only) and monkeypatch `chronicler.__file__` (via `monkeypatch.setattr(replay.chronicler, "__file__", ...)`) instead; keep both parametrized cases (`turn_artifacts.py`, `war/engine.py`) and the expected `CheckpointError`. Add a test asserting `replay._runtime_identity()["source_sha256"] == package_digest(Path(chronicler.__file__).parent)`.
- [ ] Step 3 (R6): `tests/test_shadow_oracle.py:166` string target; `tests/test_decision_delivery_adapter.py:164`; `tests/test_practice_growth_observer.py:274`; `.github/workflows/*:118/238/116/265` name only the test path and stay byte-identical.
- [ ] Step 4: If moving `validation_compare`: edit `README.md:220`, the assertion at `tests/test_native_build_lanes.py:86` (it checks the literal `python -m chronicler.validation_compare`; change both together), `scripts/m53b_run_validation.py:71`, `tests/test_procedural_gates.py:134`, `tests/test_spec_communities.py:241,290`, docs `DEVELOPMENT.md:217`, `docs/integration/oracle-followups.md:408`, `docs/integration/population-entities.md:244`. Run `scripts/m53b_run_validation.py --help` to confirm it still imports. Otherwise skip these two modules and record in DEVELOPMENT.md that they stay.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest -q tests/test_checkpoint_replay.py tests/test_turn_artifact_runner.py tests/test_diplomacy.py tests/test_techniques.py tests/test_shadow_oracle.py tests/test_oracle_gate.py tests/test_decision_delivery_adapter.py tests/test_practice_growth_observer.py tests/test_practice_growth_observer_integration.py tests/test_practice_observer_runner_integration.py` (add `tests/test_validation_compare.py tests/test_procedural_gates.py tests/test_spec_communities.py tests/test_validation_ablation.py tests/test_validation_population.py tests/test_native_build_lanes.py` if validation moved); R7 (b)-(d).
- [ ] Step 6: R8; commit.

## PR 7: Remove shims (after the first release following PR 6)
### Task LAB-1g
- [ ] Step 1: `git rm` every `src/chronicler/<name>.py` listed in `src/chronicler_lab/SHIMS`, then `git rm src/chronicler_lab/SHIMS`. `rg -n "chronicler[./](<29 names>)\b" src scripts tests docs README.md` must return only history under `docs/superpowers/` and fixtures.
- [ ] Step 2: Remove the shim tests from `tests/test_import_compatibility.py`; keep the boundary guard and make it assert `src/chronicler/<name>.py` no longer exists for each lab name.
- [ ] Step 3: Verify: `.venv/bin/python scripts/run_python_oracle_checks.py`; `.venv/bin/python -m pytest -q tests/test_import_compatibility.py`; commit `Remove chronicler_lab import shims`.

## Test placement decision
Tests stay in `tests/`. Moving them to `tests/lab/` would change `scripts/testing/native_shards_manifest.json` keys, the `additions` map and module count in `tests/test_native_ci_shards.py:190-232`, the oracle chunks (`scripts/run_python_oracle_checks.py:81-89,107,157,206-216,289-293,436-456`), the test-path hits in `tests/test_native_ci_shards.py` and the workflow lines naming `tests/test_practice_growth_observer.py` (whose bytes are mirrored in `docs/workflows/`). That is a separate, optional PR with no behavioural benefit; also several of the importing tests (`test_diplomacy`, `test_techniques`, `test_health_care_policy`, `test_validation_*`) are production tests and cannot move.

## Done when
- [ ] `src/chronicler_lab/` holds the agreed modules (27 or 29); `git log --follow` shows history.
- [ ] `rg "chronicler_lab" src/chronicler` finds only shim files (before PR 7) or nothing (after).
- [ ] The boundary guard, shim-identity and CLI shim tests pass; `load_session` reads an existing session directory through both paths.
- [ ] `checkpoint_replay` source identity still hashes the production package.
- [ ] `scripts/run_python_oracle_checks.py` passes with no chunk near 110 s; `scripts/turn_speed_identity.py compare` is identical on every PR.
- [ ] `native_shards_manifest.json`, workflows, `docs/workflows/*.yml.in` and `tests/fixtures/reference_baselines/**` show no diff.
- [ ] `uv lock --check` passes; a built wheel contains `chronicler_lab`.
- [ ] DEVELOPMENT.md, AGENTS.md, README and the module-naming docs are updated; CONTINUATION records each PR. No gate is claimed that was not run (native tests and the 200-seed gate are not applicable to this move).
