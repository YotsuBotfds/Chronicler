# Helper scripts for the 2026-11-08 plans

Read-only census helpers that the [viewer streamlining](../2026-11-08-viewer-streamlining.md) and [lab package relocation](../2026-11-08-lab-package-relocation.md) plans call:

- `viewer_exports.py`: viewer exports with no consumer, used only by tests, or used only inside their own module. Run it from `viewer/src`.
- `lab_reachability.py`: static reachability of `src/chronicler` modules from `main`, `live`, `validate` and `narration_audit`. Run it from the repository root.

Both scripts print a report and change nothing. Both use heuristics, so review every result by hand.
