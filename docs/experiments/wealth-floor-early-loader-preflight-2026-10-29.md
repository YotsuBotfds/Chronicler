# Early regression-loader preflight — source-only follow-up

This prepared patch moves the selected-Python loader check before either release
compilation. It follows the [qualified paired-build readout](../integration/wealth-floor-paired-native-build-2026-10-29.md)
while preserving producer `3bf976cd`, its cold-build evidence and the separate
readout ref `bfa33690`. It has no runtime qualification or measured wall-time
benefit; a future separately registered run is required.

After the existing pinned toolchain checks, the owned supervisor runs the same
selected interpreter's `-I -B` sysconfig query. Existing canonical path/library
validation and hashing run before either release command. The returned child
environment is discarded, leaving both normalized release environments unchanged.

`regression-loader-preflight.json` retains a bounded `passed` or `refused`
observation. Refusal records its stage and exception class without arbitrary
exception/config text. Successful publication retains the early record in the
manifest and light evidence. Query logs keep their existing bounds.

Immediately before `candidate-regressions`, the original isolated query and
path/library hash checks run again. All derived facts must equal the early
observation before the regression child can receive `LD_LIBRARY_PATH`. A changed
late observation remains in `candidate/regression-loader.json` with incomplete
publication; it cannot authorize that child or worlds.

Six fixture cases exercise the real build entry with process, resource, source
and native boundaries replaced by inert fixtures. Four unsupported setups stop
before both releases; a valid setup reaches both with identical loader-free
environments; a same-size library-byte change stops before the regression child.
All six fail against the exact qualified `3bf976cd` controller, demonstrating the
previous late ordering and single loader observation. Those are synthetic
negative controls, separate from the retained real first-build failure.

All 188 guarded cases pass in 0.66 seconds, with zero project-native imports,
runtime-factory calls or blocked I/O attempts. No actual interpreter query,
compiler, native runtime, resource probe or world ran in these new cases.

The native source pins, tool versions, release flags/profile, dependency cache
cleanup policy, process controls, D2/R44 helpers and resource floors are unchanged.
Dependency-cache reuse is excluded from this patch. The existing activation
registration is unchanged and does not match this source-only branch. No new
build or world is activated, and current proof inputs stay frozen.
