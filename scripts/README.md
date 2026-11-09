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
`docs/DEVELOPMENT.md`. `check_python_env.py` reports an environment's
interpreter, Chronicler source and `chronicler_agents` state, and with
`--expect native|no-native` exits 1 on a mismatch; `cloud_setup.sh`, `setup.sh`
and `setup.bat` run it last.

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
| `refactor_preflight.py` | Read-only map from files you plan to change or move to the witnesses, digests, workflows, importers and manifests that pin or name them (see `docs/DEVELOPMENT.md`). |
| `testing/` | Test-only guard (`python_oracle_guard.py`), source witnesses, the native shard manifest and the script smoke manifest with its runner (`script_smoke.py`). Never product code. |

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

`retail_schedule.py BUNDLE --output S.json` extracts a household retail run's pilot schedule
(its recorded open/close `intervals`, exact; or the intervals a bundle without them implies from
its frames, approximate) as the canonical JSON that `--household-retail-boundary schedule
--household-retail-schedule S.json` replays; `--strict` refuses an approximate one (see
`docs/integration/household-retail.md`).

`livelihoods_screens.py run OUT --sprint N` reruns a livelihoods sprint's preregistered screen
arms on its fixed held seeds (hybrid; run it with the native interpreter that matches the
source). `livelihoods_screens.py report OUT/metrics.jsonl --sprint N` summarizes them, with
worlds as the units and each arm paired with its declared control arm. `--sprint` defaults
to 1. The committed sprint-1 metrics are in `docs/superpowers/progress/livelihoods-sprint1-screens/`.

`connected_world_screens.py run|report|check|registry` runs the connected-world program's
screens through the generic `screen_runner.py` (seeds checked against `seed_registry.json`,
2-3 primaries, a frozen preregistration with a machine-read compute ceiling, the fixed harm
panel, activation before effects, identities). CW1–CW6 and their follow-ons are implemented;
CW6 delegates to `cw_integrated_screen.py` for its strict sidecar-aware extractor and
120-turn bounded horizon. `cw_health_screen.py` owns the separate 200-turn C2/C4 screen;
`archive/cw_program_profile.py` reproduces the serial declared-scale off/FULL profile with explicit
200-turn screen and 150-turn procedural stress cases. These are bounded evidence tools,
not qualification or default promotion. `feature_matrix.py` generates the switch compatibility matrix from the feature catalog.
See [connected-world screens](../docs/integration/connected-world-screens.md).
`archive/watershed_calibration.py BUNDLE [BUNDLE ...] [--json OUT]` compares the index the watershed
account (`--watershed`, record only) would derive with the index the simulation used;
`archive/watershed_replay.py capture|check|replay|fit|cv` captures the account's inputs, replays its
step under other constants (checked against `account_step`), fits a declared parameterization and
cross-validates it with two seeds held out (the B2 calibration); `archive/watershed_activation.py FLOW_DIR:RECORD_DIR ...`
compares `--watershed-mode flow` with `record_only` runs (development-only activation report). All
three read procedural development worlds only and refuse other seeds; see
[docs/integration/watershed.md](../docs/integration/watershed.md), sections 8 and 9.

## Bundles and viewer fixtures

`bundle_v6.py` converts, decodes and compares bundles;
`archive/prune_dead_civ_snapshots.py` prunes version-4 ones. These generators write the
checked-in fixtures in `viewer/src/__fixtures__/` that current viewer and
Python tests read. Regenerate one only deliberately and review the diff:

| Generator | Fixture | Source |
| --- | --- | --- |
| `build_transport_fixture.py [OUT]` | `transport_bundle.json` (the default OUT) | its own 10-turn `--agents off` run |
| `generate_viewer_fixture.py --write` (or `--out PATH`) | `sample_bundle.json` | its own 10-turn run |
| `build_viewer_systems_fixture.py BUNDLE OUT` | `systems_bundle.json` | an all-systems agent-mode run |
| `build_debt_holders_fixture.py BUNDLE OUT` | `debt_holders_bundle.json` | a `--domestic-credit` agent-mode run |
| `build_movements_fixture.py BUNDLE OUT [--faiths]` | `movements_bundle.json`, `faiths_bundle.json` | an `--agent-movements` run |
| `build_learning_fixture.py BUNDLE OUT --every 5` | `learning_bundle.json` | the seed 42, 500-turn hybrid `--scholarship` run |
| `viewer/scripts/build-harvest-observations.mjs`, `viewer/scripts/build-transaction-observations.py` | `harvest_forecast_observations.json`, `transaction_observations.json` (their default outputs) | decoded runs ([viewer README](../viewer/README.md#scripts)) |

`build_transport_fixture.py` with no argument rewrites its fixture; the
others need explicit arguments. The checked-in `sample_bundle.json` predates
the current writer and does not reproduce (see the script's docstring).
`cities_bundle_v6.json` is `cities_bundle.json` as `write_bundle` writes it
(`tests/test_bundle_codec.py`). `cities_bundle.json`,
`faiths_legacy_bundle.json`, `region_inspection_bundle.json`,
`scientific_claims_observations.json`, `bundle_v2/` and the `.ts` fixtures
have no generator in this repository.

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

`benchmark_headless.py` and `agent_scale_benchmark.py`
(`archive/benchmark_perception.py` and `archive/m53_baseline.py` are archived).

## Archive

[`archive/`](archive/README.md) holds one-off probes, milestone comparisons and
reports that only dated docs cite, kept for reproducing those records.
Tests and CI do not run them. `testing/script_smoke_manifest.json` records,
for each archived script and for the two fixture generators that left the
archive, a smoke invocation, its exit status, whether it writes files and
what it needs (native extension, network, inputs).
`tests/test_script_smoke_manifest.py` checks that manifest statically;
`python scripts/testing/script_smoke.py` runs the entries marked safe in a
detached temporary worktree of HEAD and fails on a changed exit status or
any file change. It shows only that those invocations exit as recorded and
write nothing, not that the scripts' results still hold.
