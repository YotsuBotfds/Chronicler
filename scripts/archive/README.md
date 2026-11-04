# Archived scripts

Moved here on 2026-11-04 from `scripts/`. Only dated records under `docs/`
cite these scripts (milestone probes, one-off comparisons, earlier reports and
fixture builders). No test, CI workflow or current setup doc uses them. Their
documented commands were updated to the new paths, and their repository-root
lookups now go up two levels, so they still run from the repository root:

```sh
.venv/bin/python scripts/archive/<name>.py --help
```

They are not covered by tests or CI and may have drifted from current source.
Before relying on one again, rerun it against the current source and move it
back to `scripts/` with a test. Git history keeps their original paths, so
older commits and receipts that name `scripts/<name>.py` still resolve at those
commits.
