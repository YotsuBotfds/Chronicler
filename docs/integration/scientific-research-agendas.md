# Finite research agendas: implementation checkpoints

The [prospective contract](../experiments/scientific-research-agendas-prospective-2026-10-28.md)
and its peer amendments were committed before runtime changes. This line is
default off and separate from main; an internal API and coherent scheduler
are still required before this foundation is usable as recurring research.

## Lazy retained-state foundation

ResearchAgendas/ResearchCycle are strict data models. ScientificClaimsState,
ProposalReceipt and ScienceMessage expose optional research/agenda metadata
through genuinely lazy backing keys. No new default Field or PrivateAttr is
inserted in legacy instances. Nested validation copies the enabled input;
serialization honors mode/include/exclude. Present null, incomplete, malformed
or unvalidated model-copy update data is rejected rather than treated as legacy.
Deepcopy, pickle and shared experiment-style reconstruction retain both enabled
and paused state; explicit equality includes lazy metadata.

The initial focused science/publication/lifecycle/state run passed 116 guarded
checks in 4.86 seconds. Subsequent state-only hardening passed 23 checks in
0.36 seconds, including paused reconstruction, mutable-list corruption and
unvalidated external updates. Both receipts record no loaded native module,
runtime calls or blocked I/O attempts. They qualify the named Python surfaces,
not a native/world gate or implemented agenda scheduler.

On Python 3.13.5, hash seed 0, a separate exact-source probe compared frozen
`b25727e3` with this foundation. All twelve raw artifacts matched: protocol-5
pickle and JSON for empty science state, proposal, message and nested worlds
before funding, with paid running trials and after publication. No fields or
bytes were stripped. This includes full raw private/cache-bearing world state
for those mechanical fixtures, not complete checkpoint files with build/path
headers. The empty legacy state remains 612 pickle bytes, SHA-256
`af3d46f9509647db6ef6b48d19f2148e2d3fa0a118040052632e8c453754df0d`.

External artifacts are under `/workspace/chronicler-science-research-evidence`:
`b257-frozen-models` and `lazy-state-final`. Their identical manifest SHA-256 is
`2400e8aec80407860ef92e32aa0d869497e4941630a4ae8d354840d35a52b440`.
The external probe `/tmp/export_scientific_raw_model_identity.py` SHA-256 is
`45396ce08f6a8961fc25330d4ff1190fabf15254ce82aa51bc20d64bfd512b0e`.
Existing natural/native research evidence was not modified or rerun.
