# Compose practice and budget default AST contracts — source only, 2026-10-29

The first9ebe CI run40968762010/1 failed after its care+budget chunk passed.
Offline job123779884814 reported90 passed/1 failed in the practice chunk;
`test_entire_default_main_AST_matches_qualified_parent` retained the original
practice-only projector. It removed two practice keywords/branches but left the
separately source-reviewed optional artifact_budget additions. Its projected
full-main AST digest413fdf291f11065e02c4fcbe5ac03927f6301f87609928a040b2a6a278bedcce
therefore differed from the qualified original8e007835bad6dbc5dd3f327d8d5a3947777f806dd5adbb8436f57b0b483fefa6.
The failedb952 and9ebe first runs are preserved; neither receives a same-source
retry. This is a retained projection-contract composition failure, not evidence
that new product/default behavior or enabled budget execution was qualified.

The narrow repair keeps BASE1205b6e48215c3e5c44d2bcb6376ca65827a7aab and the SAME
original whole-module AST digest. It does not bless today's AST. The explicit
projector now accounts for four artifact_budget=None keywords in
_write_state_checkpoint, _save_memory_streams, execute_run and _configure_run,
plus the two existing practice_observer=None keywords. Exact argument order,
annotation/type-comment and Constant(None) shapes are required in the five
functions. Unexpected keywords/defaults/annotations refuse rather than vanish.

Fourteen budget branches and two practice branches have closed canonical AST
shape pins in exact lexical scopes/order. In particular, the capture by nested
execute_run._save_exact is handled explicitly. The default branch is retained
only for the exact None predicate; non-None admission/guard additions select
their empty else. No arbitrary name/predicate/call is removed. Counts, duplicate
functions, extra/missing branches and any edited branch shape fail closed.
These local pins identify ONLY the reviewed optional branch wrappers; the final
qualification still compares every projected module node to the original BASE
hash. They do not replace that original digest with a current main hash.

Only the exact added execute_run artifact-budget parameter documentation suffix
is removed, with a required single occurrence and exact terminal indentation.
Every other docstring, documentation character, function/module/class node and
unrelated signature/body node remains. The earlier11-file budget proof stripped
all docstrings for its separate static comparison; that generic scrubber is not
used by this repair. The complete65-to-b952 main diff and both source proofs
were read before implementing the narrower combined full-module contract.

The existing pytest test functions, parametrizations and order are unchanged.
The same whole-AST case also contains two bounded prospective literal mutations:
an unrelated docstring change and an unrelated physics-call argument change
must remain visible, while the unmodified literal AST remains identical. These
are AST data checks, with no code-object execution and no additional pytest
cases. All other test-module bytes before this final function remain exact9ebe.
Actual collection/tests/CI for this child are UNRUN, regardless of metadata AST
inverse checks. Source metadata inversion is not a native/World/RNG trajectory
or enabled-output/performance observation.

Exactly three paths change: this test, this dated note and continuation prepend.
All185 product modules, native09ec,305 owners/six skips623,38 offline chunks/
335 source-pin path set/110-second limits, dependencies, workflows and chunk
selections are byte-exact9ebe. Only the changed test's source hash will move in
future builder/offline maps. No product import, compile, collection, tests,
native/World/CP/probe/build/network/GitHub/push/CI ran during source authoring.
A new isolated full-source export and object database are sealed; original
source/evidence/ref/index/permission namespaces remain untouched. Different
source review and a new child's own first CI remain necessary. Main is untouched.
