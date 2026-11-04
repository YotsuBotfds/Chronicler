# CI qualification scheduling

This source-only workflow change separates independent Rust execution from
the release-extension/Python lane. The existing **Python native** check stays
a barrier requiring both jobs to succeed. The tests, compiled-module/class
checks, release profile and complete Python selections remain intact.

Previously that lane's critical path was release build + Python tests +
debug build + Rust tests. With independent GitHub runners the proposed path
is max(release build + Python tests, debug build + Rust tests), plus setup and
the short barrier. This is a scheduling change, not a measured speedup.
Runner availability and extra setup determine its actual benefit.

Use GitHub's maintained cache action for uv artifacts and Cargo downloads.
The release lane additionally caches only `target/release`; Cargo/maturin
still run locked builds and validate their own fingerprints. Chronicler's
native extension wheel outputs are not restored from a cache; uv can cache
dependency wheels. Compiler identity, Python selection and lock/
manifest inputs name the release cache; normal Cargo checks remain required
even after a hit. The debug test target is deliberately not cached: the
local full test target grew to 8.3 GiB, much larger than the reusable wheel.

Every complete Python lane writes JUnit, and CI retains it on failure too.
The native lane records the installed compiled extension's SHA-256, actual
class checks, source commit and interpreter before calling pytest. These
receipts identify execution; they do not replace milestone seed gates or
establish scientific benefit. No workflow dispatch, PR, main merge or remote
CI result is part of this local change.

Local validation: actionlint 1.7.12 accepted the complete workflow; its
release archive SHA-256 was checked before use. All 16 combinations of
success/failure/cancelled/skipped dependencies exercised the actual Bash
barrier: only two successes passed. The native Python heredoc parsed and
executed its real compiled-module/class/hash preflight against extension
`fb20dbc8…5317`; an observed pytest call had exactly the full selection plus
JUnit output. That preflight check deliberately substituted the pytest call
and executed no test suite. Independent review found no blocking issue.
The external evidence directory is `/workspace/chronicler-ci-scheduling-evidence`.
Remote Actions execution, cache transfer cost and CI wall-time benefit remain
unmeasured. The existing workflow triggers still exclude lead-branch pushes.

After the [separate full Rust debug-info experiment](rust-debug-info-experiment-2026-10.md),
the standalone Rust job sets `CARGO_PROFILE_DEV_DEBUG=0`. All 1,088 tests and
the same two existing ignores matched baseline test names/outcomes. Compiler
artifacts verified optimization 0, debug information 0, assertions enabled,
overflow checks enabled and default features. Its fresh target occupied
1,103,060,992 uniquely allocated bytes. The older warmed target had a different
artifact history, so this is not a controlled percentage saving or speedup.
The setting belongs to the Rust test job; the release-wheel job keeps its
existing release profile. The combined native check still requires both jobs.
