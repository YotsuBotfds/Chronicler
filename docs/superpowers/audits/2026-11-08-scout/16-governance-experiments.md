## 16 Governance kernels, experiment sessions and ablation harnesses
**Map**
- 17 modules in scope, 8,421 lines (`src/chronicler/`). Reachability traced by grep of `src/`, `tests/`, `scripts/`, `viewer/`.
- Production-reachable: `governance_runtime.py` (1654 lines) is called from the turn loop (`simulation.py:537` phase-8 funding, `simulation.py:1571` `tick_governance`) and from `action_engine.py:1244`, `succession.py:71`, `commons_rules.py:198`, `agent_movements.py:979-1201`, `narrative.py:930`, `run_checkpoint.py:256`. `models.py:20` imports `governance_state.CivGovernance`.
- Governance is ON by default for new worlds: `governance_runtime.py:87` sets `DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, and the `--governance` help says "default on for new worlds" (`main.py:2156-2158`). This contradicts the brief's default-off framing for this part of the package.
- CLI-reachable, opt-in: `fork.py` (`--fork`, `main.py:2770`), `what_if.py` (via `--live`, `main.py:2783` to `live.py:1651`), `decision_ablation.py` (`--decision-ablation`, `main.py:23,2135`; agent path `agent_bridge.py:1252`), `ablation_arms.py` (hidden `--ablation-output`, `main.py:1493,2124`; its own `main()` at `ablation_arms.py:339`), `governance_metrics.py` (`analytics.py:1385`, reached by the `--analyze` report).
- Detached (no `src/` path from the CLI or turn loop): `governance_measurements.py`, `governance_capture.py`, `governance_sequence.py`, `experiment_sessions.py`, and six leaves. These are reached only from `scripts/` and `tests/`.
- Shared lane: `governance_kernel_harness.py` is imported by `governance_runtime.py:52` for `contribution_id` only (used at `governance_runtime.py:1215`). `run_kernel_frame` (`governance_kernel_harness.py:412`) is called only from `governance_capture.py:71`, scripts and tests.

**(a) Reachability table**

| Module | Lines | Reachable from |
|---|---|---|
| governance_runtime.py | 1654 | turn loop (`simulation.py:537,1571`); `action_engine.py:1244`; `succession.py:71`; `main.py:337,1651` (default on) |
| governance_state.py | 164 | `models.py:20`; `gp_agendas.py:65`; `gp_agendas_state.py:23` |
| governance_stress.py | 292 | `governance_runtime.py:60` |
| governance_kernel_harness.py | 583 | `governance_runtime.py:52` (`contribution_id` only); `run_kernel_frame` only from capture and tests |
| governance_metrics.py | 140 | `analytics.py:1385` (CLI analyze report) |
| governance_measurements.py | 1653 | scripts (`governance_measurement_report.py`), capture, sequence; no `src/` runtime import |
| governance_capture.py | 115 | `governance_sequence.py`; `scripts/governance_capture_report.py` |
| governance_sequence.py | 180 | `scripts/governance_sequence_report.py`; tests only |
| experiment_sessions.py | 1680 | six leaves below; 8 scripts; tests (no CLI) |
| session_operations.py | 360 | `scripts/session_operation.py`; tests |
| experiment_receipt_inspector.py | 239 | `scripts/experiment_receipts.py`; tests |
| memome_candidate_preview.py | 173 | `scripts/memome_candidate_preview.py`; tests |
| campaign_order_preview.py | 169 | `scripts/campaign_order_preview.py`; tests |
| session_comparison.py | 162 | `scripts/compare_experiment_sessions.py`; tests |
| snapshot_campaign_sessions.py | 117 | `scripts/snapshot_campaign_session.py`; tests |
| what_if.py | 587 | `live.py:1651-1652,1680,1729` (`--live` only) |
| ablation_arms.py | 362 | `main.py:1493` (hidden flag); `scripts/m53b_run_validation.py:66`; `validation_ablation.py:23` |
| decision_ablation.py | 58 | `main.py:23,1659`; `agent_bridge.py:1252` |
| fork.py | 75 | `main.py:2770-2771` (`--fork`) |

About 4,850 of 8,421 lines (roughly 58%) have no CLI or turn-loop path.

**(b) Detached share and archive candidates**
- The detached set is `governance_measurements` + `governance_capture` + `governance_sequence` (1,948 lines) plus the session cluster (`experiment_sessions` + six leaves, 2,900 lines).
- Moving them to a `chronicler.lab` sub-package is possible but not free:
  - `tests/test_experiment_default_boundaries.py:20` asserts `es.__file__` equals `src/chronicler/experiment_sessions.py`. A compatibility shim would fail this test.
  - `tests/test_snapshot_campaign_sessions.py:347-359`, `tests/test_snapshot_input_boundaries.py:396` and `tests/test_campaign_snapshot_adapter.py:1230` pin the `snapshot_campaign_sessions.py` path as the sole adapter consumer.
  - `tests/test_reviewed_base_submission.py:31` lists `src/chronicler/session_operations.py` as owned.
  - `tests/test_governance_sequence.py:504-513` asserts the exact import surface and the exact import closure of `governance_sequence`, and that no `src/` file mentions it.
  - `tests/test_governance_measurements.py:1070-1090` pins the import closure of `governance_measurements` by regex.
  - `tests/fixtures/reference_baselines/26e1869d.../MANIFEST.json` pins `experiment_sessions.py`, `experiment_receipt_inspector.py` and `snapshot_campaign_sessions.py`.
  - `scripts/testing/native_shards_manifest.json` pins test paths (for example `tests/test_session_operations.py`).
- Deleting rather than moving would break saved experiment session and receipt directories that `experiment_sessions.load_session` (`experiment_sessions.py:1555`) reads. Those are historical evidence.

**(c) Overlaps**
- `ablation_arms.py` (fork and checkpoint turn helpers, lines 72-107) is the producer. `validation_ablation.py:23` and `validation_io.py:2983` consume it; the layering is correct and not duplicated.
- `expansion_compare.py:37` and `kin_root_exposure.py:37` both define `_canonical` JSON helpers, but they differ (`ensure_ascii`, trailing newline). Merging them would change digests, so they are not a safe merge.
- `_utc_now` exists in `ablation_arms.py:109` and `batch_manifest.py:239`.
- `experiment_sessions.read_regular_file_bytes` (`experiment_sessions.py:1299`) and `snapshot_campaign_sessions.read_bounded_bytes` (`snapshot_campaign_sessions.py:84`) overlap in purpose; equivalence unverified.
- Experiment session receipts (`experiment_sessions`, `expansion_experiment`, `memome_experiment`) all carry fork and receipt concepts; scout 17 should confirm.

**(d) Fragility**
- Exact-resume and what-if pairs require `PYTHONHASHSEED=0` at process start (`what_if.py:224-228`). `ablation_arms.py:352` sets it only for children via `setdefault`.
- Subprocesses use `sys.executable -m chronicler.main` (`what_if.py:490`, `ablation_arms.py:224`) and inherit the environment (`what_if.py:505`, `ablation_arms.py:228`).
- Governance RNG is `random.Random(stable_hash_int(label, seed, turn, offset, ...))` (`governance_runtime.py:313`). Offsets are hand-picked constants (`governance_runtime.py:70-73`, 1000/1200/1300/1900) with no collision check.
- `governance_measurements` pins its own import closure by regex, so any refactor of its imports breaks a test.
- `governance_sequence.py` is default-off by its docstring, but `governance_runtime` is default-on; the docs and the runtime disagree about which part of governance is "experimental".

**Simulation depth**
- Governance: `governance_stress` regime classification and `governance_kernel_harness` frame logic are detached from the simulation. Wiring the capture/measurement outputs into `analytics` or the viewer would deepen the phase-8 signal.
- Ablation: `decision_ablation` supports four arms (`DECISION_ABLATIONS`, `decision_ablation.py:25`); more arms need only the native switch.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| governance_sequence.py, governance_capture.py, governance_measurements.py, plus `scripts/governance_{sequence,capture,measurement}_report.py` | archive or move to `chronicler.lab` | ~1,950 (src only) | `test_governance_sequence.py:504-513`, `test_governance_measurements.py:1070-1090`, `test_governance_capture.py`; shard manifest entries; no CLI flag; no saved-bundle compat | med |
| experiment_sessions.py + six leaves (session_operations, session_comparison, snapshot_campaign_sessions, experiment_receipt_inspector, campaign_order_preview, memome_candidate_preview) | move to `chronicler.lab` (do not delete) | 0 net (relocation); ~2,900 out of the main package | path pins `test_experiment_default_boundaries.py:20`, `test_snapshot_campaign_sessions.py:347`, `test_snapshot_input_boundaries.py:396`, `test_campaign_snapshot_adapter.py:1230`, `test_reviewed_base_submission.py:31`; reference_baselines MANIFEST; 9 scripts; deletion would orphan saved experiment session/receipt directories read by `load_session` (`experiment_sessions.py:1555`) | med (move) / high (delete) |
| governance_kernel_harness.py frame logic (`run_kernel_frame` :412 and codec :515-583) | extract `contribution_id` (:61) into governance_state or governance_runtime; move the rest with the capture lane | ~450 from the production package | `governance_runtime.py:52` imports `contribution_id`; `test_governance_kernel_harness.py`, `test_governance_dormancy.py`, `test_governance_measurements.py:1070` pin the harness closure; `scripts/governance_capture_report.py` | med |
| snapshot_campaign_sessions.read_bounded_bytes (`:84`) vs experiment_sessions.read_regular_file_bytes (`:1299`) | merge into one reader | ~20-30 (equivalence unverified) | `test_snapshot_input_boundaries.py:396`, `test_session_read_bounds.py`, `test_session_io_boundaries.py` | low |
| `_utc_now` in ablation_arms.py:109 and batch_manifest.py:239 | extract to a shared helper | ~3 | none beyond the two modules; minor value | low |
| expansion_compare._canonical (:37) and kin_root_exposure._canonical (:37) | do NOT merge | 0 | merging changes byte output and digests (ensure_ascii, trailing newline) | high |
| decision_ablation.py, ablation_arms.py (keep) | keep; do not delete | 0 | CLI `--decision-ablation`, `--ablation-start-turn`, hidden `--ablation-output`; saved `metadata.decision_ablation` (`main.py:1535,1969`) and resume path (`main.py:1994`); `scripts/m53b_run_validation.py` | high if touched |
| fork.py, what_if.py (keep) | keep | 0 | `--fork` (`main.py:2770`), `--live` (`main.py:2783`) | high if touched |

**Confidence**
- Verified by grep and by reading the import sites and defining lines for every module. Not verified: full test runs (none run per the brief), the bodies of the duplicated helpers beyond their signatures, and whether `analytics` is reached only from the `--analyze` path. Scout 17 should check the validation/expansion overlap in depth.
