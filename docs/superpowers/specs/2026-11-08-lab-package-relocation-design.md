# `chronicler_lab` Package Relocation — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** LAB-1 (input decision: DEC-6)
> **Depends on:** DEC-6 (move vs delete; package name; two sub-decisions in section 3.1). Independent of PIN-1: no moved file has an enforced pin.
> **Feeds:** DEAD-2 (fewer unpinned symbols to vet), DEP-9 (leaves `validation_compare` in place unless DEC-6 says otherwise), CON-12
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (Wave 3) + scout 16, 25(d), 27, 14, 10, 17, 18

## 1. Goal and scope
Move the detached harness modules out of the production import namespace into a sibling package `src/chronicler_lab/`, one cluster per PR. This is a relocation, not a deletion. Nothing changes in simulation, RNG, saved bundles or CLI flags. Old import paths keep working through a short-lived shim layer.

Not in scope: moving tests (they stay under `tests/`), moving scripts (they stay, only their imports change), any edit to function bodies, deleting any module.

## 2. Current behaviour (re-derived, verified)
**Reachability.** I wrote an AST import graph (absolute, relative, `from chronicler import x`, literal `import_module`, in-function imports; script `docs/superpowers/plans/2026-11-08-tools/lab_reachability.py`). Roots: `main`, `live`, `validate`, `narration_audit`. The only entry point in `pyproject.toml` is `chronicler = "chronicler.main:main"` (`pyproject.toml:19`); there is no `__main__.py`. Literal-only analysis finds 33 unreachable modules. Four extras are **false positives**: `learning_cohorts`, `remittances`, `timber_orders`, `wealth_accounting` are loaded by name through `import_module("chronicler." + name)` (`livelihoods.py:685`, `wealth_accounting.py:182`, `expansion_features.py:125`). **The scout's 29 are correct.** Total is 13,879 lines (`wc -l`), not 13,880. None of the 29 appears as a quoted string anywhere in `src/` outside its own file, so no dynamic production import reaches them.

**Direction of dependencies.** The 29 import production modules (`models`, `simulation`, `world_gen`, `artifact_io`, `campaign_logistics`, `turn_artifacts`, `bundle_codec`, `governance_kernel_harness`, `institutions`, ...) and each other. Production never imports them. Five of them use **relative** imports of production siblings: `governance_measurements.py:48-52`, `governance_capture.py:10-11`, `governance_sequence.py:11-12`, `kin_root_exposure.py:15`, `community_admissibility.py:16-17`. These must become absolute when moved.

**Entry points by `python -m`.** Seven modules have `__main__` blocks: `expansion_audit`, `validation_compare`, `expansion_compare`, `history_forensics`, `evidence_admission`, `checkpoint_replay`, `community_admissibility`. Callers: `README.md:220`, asserted by `tests/test_native_build_lanes.py:86`; `docs/DEVELOPMENT.md:217`; `docs/checkpoint-replay.md:12`; `docs/validation/evidence-admission.md:5`; `docs/integration/history-forensics.md:15`; `docs/integration/community-admissibility.md:6`; subprocess test `tests/test_checkpoint_replay.py:351`.

**Live callers outside the package.** `validation_compare` is used by `scripts/m53b_run_validation.py:71`, which `.github/workflows/validation-gate.yml:108` runs. `checkpoint_replay` backs production-behaviour tests (`tests/test_diplomacy.py:664`, `tests/test_techniques.py:538`, `tests/test_turn_artifact_runner.py:16`) and `scripts/a01_acceptance.py:227`. So "unreachable from production" is not "unused".

**Importers.** 21 scripts and 50 test files (25,241 lines, including 2 helper modules `tests/kin_*_contract_cases.py`) import them. The scout's 27 files / 13,669 lines counted only 13 modules.

**Disk formats.** `experiment_sessions.py:15` states no pickle; `CONTRACT = "chronicler-experiment-session-v1"` (`:46`) is a string, not a module path. No module in the 29 emits its own dotted module path into saved data (grep of `__module__`, `getsource`, `"chronicler.` literals: none). `load_session` (`:1555`) reads by file path. So on-disk session and receipt directories are unaffected by a move.

**Source identity trap.** `checkpoint_replay.py:144` uses `package_digest(Path(__file__).parent)`. After a move this would hash `chronicler_lab/` instead of production source and silently weaken the checkpoint-mismatch guard (`tests/test_turn_artifact_runner.py:219-233` exercises it). It must hash the `chronicler` package.

## 3. Design
### 3.1 Decision frame (DEC-6)
- **Move, not delete** (recommended). Deleting orphans saved session and receipt directories and ~25k test lines.
- **Name.** `chronicler_lab` (scout's name). Caveat: `lab_academy.py` and `lab_transport.py` already exist in production (`lab_academy.py:39`) and are unrelated to this package. Alternative: `chronicler_detached`. Pick one before PR 1; the plan uses `chronicler_lab`.
- **Sub-decision A:** keep `validation_compare` and `community_admissibility` in `chronicler` (they are operational validation tooling tied to CI, README and `validation_*`), making the lab set 27 modules. Recommended; DEP-9 edits validation code. Default in the plan: they move last (PR 6) and PR 6 is skippable.
- **Sub-decision B:** shim lifetime (3.3).

### 3.2 Packaging
`pyproject.toml` has `hatchling` and no package config (`:30-34`); hatchling would auto-pick only `src/chronicler`. Add:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/chronicler", "src/chronicler_lab"]
```
The existing editable install is a path entry for `src` (`.venv/.../_editable_impl_chronicler.pth` contains `<repo>/src`), and `pytest` sets `pythonpath = ["src"]` (`pyproject.toml:26`), so `chronicler_lab` imports without reinstalling. Scripts add `src` themselves (`scripts/experiment_session.py:21` pattern). `uv.lock` is unaffected (verify with `uv lock --check`). The oracle guard (`scripts/testing/python_oracle_guard.py`) blocks only `chronicler_agents*`, network and child processes; it needs no change. `chronicler_lab/__init__.py` stays empty (no side effects). Dependency direction is one-way: `chronicler_lab -> chronicler`.

### 3.3 Compatibility shims
Per-module file at the old path (not a `chronicler/__init__` hook, which would add code to every production import):
```python
"""Deprecated path; the module lives in chronicler_lab.<name>. Removed in PR 7."""
import sys
from chronicler_lab import <name> as _m
# only for the 7 CLI modules:
if __name__ == "__main__":
    raise SystemExit(_m.main())
sys.modules[__name__] = _m
```
I probed this in a scratch package: `import old.m`, `from old import m`, `patch("old.m.X")` and `python -m old.m` all hit the single new module object. Consequences: (1) string monkeypatch targets such as `tests/test_shadow_oracle.py:166` keep working with no edit, but PRs repoint them anyway so shim removal is a no-op; (2) module-object patches (`monkeypatch.setattr(es, ...)`) work by identity; (3) `module.__name__` becomes `chronicler_lab.X`. Lifetime: until the first tagged release after PR 6, then PR 7 deletes all shims. No `DeprecationWarning` (several tests run subprocesses with strict stdout/stderr).

### 3.4 Edits inside moved files
Only imports change: relative imports become `from chronicler import ...`; lab-to-lab imports become `from chronicler_lab import ...`; `checkpoint_replay.py:144` becomes `package_digest(Path(chronicler.__file__).parent)` (add `import chronicler`). No function body changes, no RNG use changes.

### 3.5 Permanent boundary guard
A new test in `tests/test_import_compatibility.py` (already owned by a shard, so no manifest churn): AST-scan `src/chronicler` (excluding shim files listed in `chronicler_lab/SHIMS`), assert nothing imports `chronicler_lab`, and no quoted string equals a lab module name. This replaces the one-off audit.

## 4. Compatibility
Saved bundles, checkpoints, CLI flags and viewer: unchanged. Import paths: old paths work via shims until PR 7. `python -m chronicler.<7 modules>` works via shims; docs switch to `chronicler_lab`. Existing session/receipt directories load unchanged. Run-checkpoint `package_digest` (`batch_manifest.py:349`) hashes `src/chronicler/*.py`; every move changes it, so run checkpoints saved before the PRs will report a source mismatch, as after any source edit (no new class of break).

## 5. Pins and preflight
`refactor_preflight.py --move src/chronicler/X.py:src/chronicler_lab/X.py` was run for all 29 (JSON in the work dir). **No enforced pin on any of the 29.** Findings:
- **Digest** (recorded hash equals current): `experiment_sessions`, `campaign_snapshot_adapter`, `memome_experiment`, `experiment_receipt_inspector`, `campaign_order_preview` (reference_baselines `MANIFEST.json`); `evidence_admission`, `shadow_oracle` (`tests/fixtures/performance/corrected_*.json`, frozen provenance). `tests/reference_baselines.py:7-14` verifies only the stored fixture copies, so a move does not break it. Do not edit the manifest.
- **Path/AST-pin tests to repoint** (read the file at its old path): `tests/test_experiment_default_boundaries.py:20`, `tests/test_snapshot_campaign_sessions.py:347,359`, `tests/test_snapshot_input_boundaries.py:396` (AST-compares to the baseline, keep the baseline key old), `tests/test_campaign_snapshot_adapter.py:1191,1218,1230`, `tests/test_reviewed_base_submission.py:31`, `tests/test_governance_sequence.py:504,516`, `tests/test_governance_measurements.py:1084`, `tests/test_memome_candidate_preview.py:28`, `tests/test_campaign_order_preview.py:27`, `tests/test_memome_experiment.py:251`, `tests/test_experiment_sessions.py:31`.
- **Import-closure assertions** listing `chronicler.X`: `tests/test_experiment_receipt_inspector.py:350`, `tests/test_governance_measurements.py:1069`, `tests/test_campaign_snapshot_adapter.py:1045,1176`, `tests/test_session_comparison.py:440-449`, `tests/test_health_care_capture.py:600`, `tests/test_decision_delivery_adapter.py:164`, `tests/test_practice_growth_observer.py:274`.
- **Test files** carry only native-shard-owner and oracle-chunk pins (`scripts/testing/native_shards_manifest.json`, `scripts/run_python_oracle_checks.py:81-89,107,157,171,206-216,289-293,436-445`). They stay in place, so neither changes.
- `.github/workflows/native-two-shards*.yml`/`tests.yml:116,265` name `tests/test_practice_growth_observer.py::...`; staying put keeps their bytes (and the `docs/workflows/*.yml.in` copies) unchanged.
- Source-identity globs (`scripts/benchmark_headless.py:206`, `scripts/a01_acceptance.py:259`) cover `src/chronicler` only; future receipts will not include `chronicler_lab`. Record this in DEVELOPMENT.md.
- `scripts/testing/script_smoke_manifest.json` notes name modules (`:47`, `:102`); update text only.

## 6. Classification
Behaviour-preserving refactor. Proof per PR: the focused test files for the cluster, the oracle lane, `scripts/turn_speed_identity.py run/compare` (production bytes untouched, so it must be identical), and the boundary guard. No correction, no baseline, no CONTINUATION behaviour entry beyond a one-paragraph structural note.

## 7. Tests
Changed: ~50 test files (import lines; path pins above). New: boundary guard, shim-identity test (`import chronicler.X is chronicler_lab.X` for every shim, plus `-m` smoke for the 7 CLI shims run as a subprocess with `PYTHONPATH=src`), and a `checkpoint_replay` source-identity test asserting the digest equals `package_digest(chronicler dir)`.

## 8. Risks, open questions, rollback
- Hidden `-m`/path users outside the repo: unverifiable; shims cover them until PR 7.
- Tests that open `src/chronicler/<name>.py` now find a 5-line shim; any missed one fails loudly.
- `kin-decision-capture.yml` runs `hosted_kin_capture.py` with `PYTHONPATH=src:.`; `kin_root_exposure`/`decision_delivery` resolve via `src`. Not run locally (unverified).
- Whether the oracle-lane subprocess tests actually run under the guard: unverified.
- Rollback: each PR is a `git mv` plus import edits; revert the PR.

## 9. Size
About 13.9k lines relocated (`git mv`, history kept), about 150 lines of shims added, about 450 import lines edited across 71 scripts/tests and ~30 docs. Seven PRs: scaffold, sessions, governance, expansion/science, health care, misc, shim removal.
