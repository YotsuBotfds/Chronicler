# Archived scripts

Moved here on 2026-11-04 from `scripts/`. Only dated records under `docs/`
cite these scripts (milestone probes, one-off comparisons, earlier reports and
fixture builders). No test or CI workflow runs them. Their documented commands
were updated to the new paths, and their repository-root lookups now go up two
levels, so they still run from the repository root.

Read a script before running it. Their command lines predate the archive and are
not uniform: several do not accept `--help` (some treat it as a path or a run
label), one needs the native extension, and `generate_viewer_fixture.py`
ignores arguments and rewrites `viewer/src/__fixtures__/sample_bundle.json`.

Two are still fixture sources: `build_learning_fixture.py` produced
`viewer/src/__fixtures__/learning_bundle.json` and `generate_viewer_fixture.py`
produced `viewer/src/__fixtures__/sample_bundle.json`, both of which current
viewer tests read. Regenerate those only deliberately, and review the fixture
diff.

They are not covered by tests or CI and may have drifted from current source.
Before relying on one again, rerun it against the current source and move it
back to `scripts/` with a test. Git history keeps their original paths, so
older commits and receipts that name `scripts/<name>.py` still resolve at those
commits.
