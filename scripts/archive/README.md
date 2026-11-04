# Archived scripts

Moved here on 2026-11-04 from `scripts/`. Only dated records under `docs/`
cite these scripts (milestone probes, one-off comparisons and earlier
reports). No test or CI workflow runs them. Their documented commands were
updated to the new paths, and their repository-root lookups now go up two
levels, so they still run from the repository root.

Read a script before running it. Their command lines predate the archive and
are not uniform. [`../testing/script_smoke_manifest.json`](../testing/script_smoke_manifest.json)
records, per script, a smoke invocation and its exit status, whether it
writes files, and what real use needs (native extension, network, inputs).
Without the native extension, 23 of the 35 Python scripts here print usage
for `--help` and exit 0. `curator_spread.py`, `epidemiology_stats.py`,
`finance_identity.py`, `narration_coverage.py`, `scholarship_probe.py` and
`viewer_systems_identity.py` print their docstring and exit 2.
`agent_movements_report.py`, `guilds_report.py`, `m_af1_compare.py` and
`scholarship_report.py` treat `--help` as a path and exit 1. `guilds_probe.py`
treats it as a batch directory, prints an empty table and exits 0.
`mutual_aid_control_snapshot.py` imports the native extension and exits 1
without it. `world-laboratory-example.sh` prints usage and exits 2.
`python scripts/testing/script_smoke.py` reruns every entry marked safe in a
detached temporary worktree of HEAD and checks that nothing changed there.

`build_learning_fixture.py` and `generate_viewer_fixture.py` were archived
with them and moved back to `scripts/` the same day. They generate
`viewer/src/__fixtures__/learning_bundle.json` and `sample_bundle.json`, which
current viewer tests read; see
[scripts/README.md](../README.md#bundles-and-viewer-fixtures).
`generate_viewer_fixture.py` now writes only with `--out PATH` or `--write`
(before, any invocation rewrote `sample_bundle.json`).

`tests/test_script_smoke_manifest.py` only checks that the manifest lists
each script here; the scripts may have drifted from current source. Before
relying on one again, rerun it against the current source and move it back
to `scripts/` with a test. Outside the archive the smoke manifest lists only
fixture generators, so drop the script's entry unless it is one. Git history
keeps their original paths, so older commits and receipts that name
`scripts/<name>.py` still resolve at those commits.
