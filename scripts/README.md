# Scripts

Operator, qualification and research tools. Run them from the repository root
with the project interpreter (`.venv/bin/python scripts/<name>.py --help`).
Many tests import these modules as `scripts.<name>` or load them by path, and
CI workflows call several by exact path, so renaming or moving a script needs
matching test and workflow edits. Experimental drivers stay default-off: their
default invocation executes nothing or writes only to stdout.

## Setup

`cloud_setup.sh` installs the locked dependencies for a Claude Code cloud
session (or a fresh Linux checkout) and prepares a separate native venv; see
`docs/DEVELOPMENT.md`.

## Gates, CI lanes and qualification

| Script | Purpose |
| --- | --- |
| `run_python_oracle_checks.py` | Bounded offline Python lane in guarded chunks (see `docs/DEVELOPMENT.md`). |
| `python_qualification.py` | Fixed full pytest lane with immutable execution evidence. |
| `m53b_run_validation.py` | Canonical validation profiles and the 200-seed gate runner. |
| `run_oracle_gate.py`, `m58b_convergence_gate.py` | Hybrid-versus-aggregate and convergence gates. |
| `native_ci_shards.py`, `native_wheel_receipt.py`, `native_release_cache.py` | Native CI shard ownership, wheel receipts, dormant cache adapter. |
| `ci_critical_path.py`, `ci_artifact_intake.py` | Offline CI timing analysis and bounded artifact intake. |
| `hosted_native_functional_smoke.py`, `hosted_kin_capture.py` | Opt-in hosted workflows. |
| `benchmark_named_context.py`, `paired_context_benchmark.py` | Opt-in compiled-context benchmark workflows. |
| `testing/` | Test-only guard (`python_oracle_guard.py`), source witnesses and the native shard manifest. Never product code. |

## Identity checks

Each proves that a feature switched off, or a performance change, leaves
simulation output byte-identical: `*_identity.py` (agent movements, cities,
diplomacy, epidemiology, guilds, historiography, languages, narration,
provenance, scholarship), `checkpoint_identity.py` (exact resume) and
`turn_speed_identity.py`.

## Reports and probes over existing runs

`*_report.py` (diplomacy, great-person agendas, maritime, nomads, techniques,
world systems), `domestic_credit_probe.py`,
`grain_reserves_probe.py`, `history_forensics.py`,
`crisis_distribution_summary.py` and `narration_prompts.py`.

## Bundles and viewer fixtures

`bundle_v6.py`, `prune_dead_civ_snapshots.py` and the `build_*_fixture.py`
builders for the viewer's checked-in fixtures.

## Examples and demonstrations

`create_example_worlds.py`, `institution_pressure_example.py`,
`crisis_*_example.py`, `campaign_*.py`, `memome_*.py`, `mutual_aid_*.py`.

## Experiments, sessions and evidence tools

Detached experiment and session CLIs (`admit_experiment.py`,
`experiment_session.py`, `session_operation.py`, `snapshot_campaign_session.py`,
`verify_snapshot_session.py`, `compare_experiment_sessions.py`,
`experiment_receipts.py`), detached governance drivers (`governance_*_report.py`),
registered experiments (`run_expansion_experiment.py`,
`economy_coupling_experiment.py`, `shortfall_priority_evaluation.py`,
`crisis_held_evaluation.py`, `scientific_*`, `wealth_floor_*`,
`qualify_third_wave.py`, `third_wave_controls.py`, `a01_*`,
`validate_fishery_recovery.py`, `experiment_rust_debug_info.py`,
`capture_kin_root_exposure.py`, `profile_ablation_writer_cadence.py`) and
`archive_parent_extras.py` for lossless parent-extra archives.

## Benchmarks

`benchmark_headless.py`, `benchmark_perception.py`, `agent_scale_benchmark.py`
and `m53_baseline.py`.

## Archive

[`archive/`](archive/README.md) holds one-off probes, milestone comparisons and
reports that only dated docs cite. They are kept runnable for reproducing
those records but are not maintained by tests or CI.
