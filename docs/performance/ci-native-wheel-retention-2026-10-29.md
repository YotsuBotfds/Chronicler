# Retain the native wheel already built by CI

The separate `lead/ci-native-wheel-retention-20261029` branch retains the
release wheel from the existing native Python job. Previously CI retained
the installed extension's identity and JUnit results, then discarded the
wheel. A later investigation could inspect the reported hash but could not
retrieve that exact build from the standard workflow.

The existing compiled-module suffix and three real class checks still run
before pytest. A small stdlib helper then requires exactly one built wheel,
streams its complete SHA-256, and verifies that its one matching native member
has exactly the installed extension's length and SHA-256. Missing, ambiguous
or mismatched files fail this new provenance check. The receipt records source
commit, wheel/native identities, interpreter and checked class names.

A separate `native-wheel-<source>` artifact retains that manifest and the
original wheel for 14 days. The original test-result artifact, full Python
selection, Rust/native barrier, locked release build, caches and all other
lanes remain unchanged. Upload runs after failures too: a wheel without a
manifest or with a failed producer is incomplete evidence, not a qualified
build. Official artifact metadata/digest and the completed producer still
need checking when consuming it.

This enables retrieval and explicit future development reuse; it adds no
automatic build skip, wheel cache, cross-head acceptance or scientific grant.
Compiler flags, full build context and native state compatibility are not
certified by this small receipt. Matching versions alone remain insufficient
for reproducibility or historical scientific-baseline reuse. Offline/no-Rust
lanes continue to require the extension's physical absence.

The focused guarded selection passes **27 tests in 0.17 seconds**: thirteen
new receipt/workflow cases and fourteen existing build-lane contracts. It
checks complete wheel/member linkage, missing/ambiguous inputs, mismatched
payloads, exact source identity and unchanged full test invocation. The guard
records zero native imports, runtime factory calls and blocked I/O. A new small
offline chunk preserves the existing 110-second limit. The tests use inert
bytes and do not claim compiled execution. Actual wheel production/upload
will be qualified on the later consolidated native candidate's own CI run;
no local native build, benchmark or world ran here.
