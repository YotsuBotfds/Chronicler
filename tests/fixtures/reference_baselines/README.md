# Historical comparison fixtures

These are exact project source bytes exported from immutable commits already
contained in the recovered Chronicler history. They are test inputs, not current
runtime implementations. The manifests record every original path, byte count
and SHA-256; `tests/reference_baselines.py` verifies them before use.

- `26e1869da6c963108f0eb09dae1455245c030bc9`: accepted Q source dependencies,
  five CLI entry points and the snapshot reader's original assertion source.
  Test source uses a `.py.txt` suffix to prevent duplicate pytest collection.
- `2ab3b4814abb665c7b3d5c255152cf5767bbf25a`: pre-A01 simulation source for
  exact two-turn event/state/narration/RNG and raw snapshot-consumer comparisons.

The fixtures replace sibling worktrees and `git show` dependencies, so full
comparisons run in GitHub's shallow checkout and on another machine. Historical
source is deliberately unchanged. The root `.gitattributes` preserves its bytes
across Windows and POSIX checkouts. Existing comparisons and negative controls
remain mandatory; a missing or mismatched fixture fails the tests.
