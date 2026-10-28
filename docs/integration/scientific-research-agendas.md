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
