# Finite research agendas: implementation checkpoints

The [prospective contract](../experiments/scientific-research-agendas-prospective-2026-10-28.md)
and its peer amendments were committed before runtime changes. This line is
default off and separate from main. The internal scheduler/API checkpoint is
implemented below; shared CLI wiring and broader/native qualification remain
separate follow-ups.

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

## Coherent internal scheduler and observation checkpoint

The explicit API is
`chronicler.scientific_research.set_research_agendas_enabled(world, bool)`.
It validates retained state before activation or pause. Core tick, confidence,
adoption and summary paths dispatch on substate **presence**, including when
paused. Absent research still follows the old path. Shared CLI/harness control
surface is not claimed complete at this checkpoint.

Canonical topic reuse, actual agenda question keys, per-cycle original/replica
membership and closed-cohort delivery are implemented. The measurement
`cohort` and original effort `started_turn` never advance. New windows have
explicit origin/lag/arrival/date checks; adopted legacy work retains its own
late-funding/dynamic-delivery rules and unknown opening roster/deadlines.

Capacity records distinguish committed rows from outstanding reservations.
Unpaid slots release when funding closes; already-paid running/publication
receipt obligations survive until delivery, actual expiry or an impossible
publication. Pending messages are a subset of owed receipts, not duplicate
capacity. Reservations are storage, not earmarked cash: every actual payment
still uses projected treasury and accumulator `keep` semantics.

Malformed controls/counters, raw grants, duplicate messages, impossible dates,
overlapping funding windows and broken references are rejected before tick/
effort guards, payments or backing attachment mutate. Current allowance rows
carry genuinely lazy `claim_id`, set at Phase 4 payment. Legacy rows remain
unknown; new current-context beliefs cannot overwrite that paid identity.
Allocation provenance cites the actual local renewed question and evidence.
Next-turn partial Phase 4 state cannot be relabelled as the prior snapshot.

New-mode summaries freeze version 1 / `finite-retained-v1`, current/open cycle,
actual dates, planned windows, used/reserved/limit capacities, reasoned unfilled
slots, archive counts and non-inferred historical completeness. They select
canonical current-context policy rows without silent clipping. Retained raw
state is distinct from the snapshot's source-turn-only resolution details.

**186 focused guarded checks passed in 10.48 seconds**, covering the existing
pilot/publication and experiment seams plus new state, lifecycle and mechanics.
No native module, network/child-process attempt or oracle runtime call occurred.
Mechanical cases include fourteen trials over several cycles; same-topic work
at another academy after its first origin falls; explicit new-academy knowledge;
all forty paid trials retained at capacity (80 trial treasury); ordinary info
controls; replay aliases/shared blocks; context A→B→A; pause/resume and exact
Python checkpoints; late actual publication; phase-order/canonical-paid-topic
separation; and pending/already-applied projected treasury.

The legacy raw-identity probe was repeated after these hooks. All original
twelve artifacts still matched frozen b257. A second independent probe added
standalone paid allocation and a nested world with source-12 payments: both
pickle and JSON matched, bringing the comparison to **sixteen artifacts** with
no stripping. The allocation remains 283 pickle bytes, SHA-256
`0106847e7c276281aa96d401c39333330001653e7859f6de87ef95000a734162`.
The four added artifacts' identical manifest SHA-256 is
`85ffb32125c2b55ef593193d8647525be857f4f81c2f40e9c154c879145d88e6`;
external probe SHA-256
`1a634c32836bb9a21dbba798afadd4f85db6a4e1544752c5cafb920e2ec3e353`.
Evidence folders are `b257-frozen-paid`, `coherent-legacy-paid` and
`coherent-legacy-models` under the same external evidence root above.

These are bounded controlled Python mechanics and compatibility proofs. They
do not qualify natural recurrence, native composition, scientific efficacy or
default activation. The known two-season paid-use gap and finite storage/
institution limits remain as registered; no threshold was tuned from outcomes.

## Scholarship registry identity boundary

Research activation now lazily binds the plan to its actual scholarship
registry and retains up to twenty immutable enrolled academy birth records.
The deterministic seal uses declared world/activation/birth data, without
simulation RNG, UUIDs or process identity. It is a producer identity boundary,
not authentication. Scholarship reset creates an unsealed registry; retained
science never binds itself to that replacement, including when a newly reused
seat zero has identical founding fields. Changed enrolled births also reject
before guards, cached grants or payments. Fall, level, scholars and current
lord remain mutable circumstances, not identity. Ordinary admission appends
one new birth record with its new seat index.

The original host can be restored through nested JSON, Python pickle or deep
copy. An absent host leaves science dormant and permits an explicit research
pause without deleting knowledge; enabling paid research again requires the
original host. A present replacement registry fails closed. The snapshot v1
shape is unchanged by this internal persisted identity metadata.

**269 focused guarded checks passed, 2 skipped, in 9.26 seconds**, including
the existing scholarship, science/publication/experiment suites and identity
counterexamples. The guard loaded no native modules and blocked no I/O; the
scholarship suite made six ecology and six politics Python-oracle factory
calls. A smaller state/mechanics selection passed 84 checks in 1.81 seconds
without those runtime calls.

The frozen b257 raw-byte probe was repeated after changing ScholarshipState's
base to the same lazy serialization wrapper. All sixteen prior files remained
exact. Standalone empty/seeded scholarship JSON and pickle added four exact
files, for **twenty raw artifacts** without stripping. Empty scholarship pickle
is 483 bytes, SHA-256
`d37e707c3685353827bec1f91ea1c059315a263f4b908aaca0c07a72fb4fa5a3`.
The four-file scholarship manifest SHA-256 is
`917b705c2a5ce635a612333861ab9f36cc9915767c37ba00d54f2bc49809cafd`;
the external probe SHA-256 is
`d94ad72090574924ec13cff88345176b5521b862b10da440b454dae1817b9244`.
The evidence root retains `b257-frozen-scholarship` and the three new
`host-bound-legacy-*` folders alongside earlier unchanged probes.

## Shared run configuration

`--scientific-research-agendas` explicitly activates finite research after
`--scientific-claims --scholarship --techniques`. The negative flag pauses new
research and retains the archive; `--no-scientific-claims` remains the separate
whole-system clear. Single, batch, live and gate command generation share
the same tri-state forwarding. Omission preserves loaded plans and adds no
research key to legacy simulation configuration or checkpoint feature flags.
Present finite plans record their effective enabled/paused setting.

Exact resume adopts the actual retained setting, including old checkpoints
whose configuration has no new key. A contradictory explicit flag rejects
instead of changing policy during an exact continuation. A research policy
intervention must use the separately declared experiment-fork seam.

The existing `expansion_experiment` request accepts the source-owned boolean
`controls.research_enabled` for enabled science. It calls the validated API;
mode/lineage are never assigned as arbitrary controls. All controls, archive,
host identity, parent checkpoint and registration are validated before mutation.
The old four `controls_before`/`controls_after` fields stay unchanged. A separate
`research_policy` receipt records before/after legacy or finite mode, actual
activation, cycle memberships and host/birth lineage, plus the requested switch.
`execute_run` records the effective run configuration and the existing
`experiment-fork` lineage with `exact: false`, actual turn and parent checkpoint.

For a direct API caller, the intervention request is:

```python
request = {
    "schema_version": 1, "experiment": "research-policy", "cohort": "development",
    "feature": "scientific_claims", "arm": "pause", "fork": True,
    "controls": {"research_enabled": False},
    "parent_checkpoint": {"path": "/path/to/parent.ckpt", "sha256": parent_sha256},
}
execute_run(args, checkpoint_resume=loaded_parent, expansion_experiment=request)
```

The optional experiment harness flag initializes the common science parent:

```sh
python scripts/run_expansion_experiment.py --feature scientific_claims \
  --scientific-research-agendas --cohort development --seeds 42 \
  --turns 60 --fork-turn 4 --workers 1 --output-root /new/evidence/directory
```

Resumed arms inherit the actual parent policy rather than forwarding an initial
flag that might conflict with a later declared parent intervention. Research
activation inside a comparison window intentionally blocks a strict matched
science contrast; enable it in the common parent before information-control
forks. The harness rejects a requested initial research mode against a source
that does not support it. With the new flag omitted, old source-run manifests
and argument lists retain their previous shape.

**70 focused guarded checks passed in 2.80 seconds** for policy intervention and
existing control/harness behavior. This includes an actual three-turn aggregate
entrypoint/checkpoint fork proving nonexact receipt/header/lineage and effective
configuration, plus mutation-free failures for malformed controls, wrong parent,
changed registration and missing/replaced host. Shared wiring separately passed
93 checks in 2.47 seconds. These do not replace the pending registered native
composition proof.
