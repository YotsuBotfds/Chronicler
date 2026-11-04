# Archived scripts

Moved here on 2026-11-04 from `scripts/`. Only dated records under `docs/`
cite these scripts (milestone probes, one-off comparisons and earlier
reports). No test or CI workflow runs them. Their documented commands were
updated to the new paths, and their repository-root lookups now go up two
levels, so they still run from the repository root.

Read a script before running it. Their command lines predate the archive and are
not uniform: several do not accept `--help` (some treat it as a path or a run
label), and `mutual_aid_control_snapshot.py` needs the native extension to
import.

`build_learning_fixture.py` and `generate_viewer_fixture.py` were archived
with them and moved back to `scripts/` the same day. They generate
`viewer/src/__fixtures__/learning_bundle.json` and `sample_bundle.json`, which
current viewer tests read; see
[scripts/README.md](../README.md#bundles-and-viewer-fixtures).
`generate_viewer_fixture.py` now writes only with `--out PATH` or `--write`
(before, any invocation rewrote `sample_bundle.json`).

They are not covered by tests or CI and may have drifted from current source.
Before relying on one again, rerun it against the current source and move it
back to `scripts/` with a test. Git history keeps their original paths, so
older commits and receipts that name `scripts/<name>.py` still resolve at those
commits.
