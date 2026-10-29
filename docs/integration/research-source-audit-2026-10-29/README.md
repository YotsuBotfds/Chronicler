# C76 finite-research source audit — 2026-10-29

**No concrete legitimate-state host/birth or canonicalization failure was found
in the traced ordinary lifecycle.** Later-cycle evidence can reach paid use
within 180 turns, but this audit establishes no natural occurrence or benefit.
Source is frozen `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`; the shared checkout
remained clean and unchanged. [audit.json](audit.json) records exact paths, byte
counts, SHA-256, Git blob IDs/modes and source references for 22 inspected files.

Scholarship founding appends a new seat (`scholarship.py:764`). Falls retain the
old entry (`:643`); rebuilding after recovery appends another. Conquest updates
`lord` (`:346`), while flight changes refugees/carries. These paths preserve
`region`, `kind`, `founded_turn`, `founder` and `name`. No current production
writer renames `Seat.name` or reorders the seat registry. **This is an immutable
writer convention, not a frozen Python object:** the models do not use
`frozen=True`. Retained-birth validation detects unsupported changes.

Research enrollment appends the seat ID and exact birth together
(`scientific_research.py:597`). Its host seal is an activation binding, checked
against the stored scholarship identity (`:47`), never recomputed from the
subsequently growing registry. Ordinary new seats therefore preserve the host.
Explicit scholarship reset drops that binding; refusal to attach an old archive
to its replacement is intended fail-closed behavior.

Payment uses the region's **current controller**, rather than birth founder or
cached patron (`scientific_claims.py:59`). Traced conquest/secession/restoration
paths preserve region indexes and retain or append civilization indexes. Scenario
renaming occurs during initialization and preserves indexed birth fields; faith
reference migration changes `seat.faith`, outside the birth record.

Canonical topic keys include recipe and full registered context/protocol
(`scientific_research.py:20`). Opening reuses matching topics (`:448`); policy
selects known topics matching the current context, including closed cycles
(`:361`). Retained informative evidence has no use-age expiry
(`scientific_claims.py:455`); the six-turn lifetime limits message delivery.
Exact topic reuse and current-context filtering prevent duplicate ordinary
recipe votes. This permits later-cycle evidence to affect an earlier canonical
policy topic when the required context recurs.

**Cadence is a prospective design coupling when interpreting the study.**
Paid turns are `started_turn + 6k` (`scientific_claims.py:523`), while season is
`(turn % 12) // 3` (`resources.py:340`). An unchanged anchor reaches exactly two
opposite seasons; claims in the other two seasons cannot receive paid
allocation under that cadence. This is not an observed natural bug or a reason
to waive a gate, resample seeds, alter eligibility or change cadence.

A conditional default-calendar example shows there is no universal later-use
block: assume hypothetical first opening/anchor **0** and undelayed later
opening **25**, with required context/access retained. With period 75 and offset
0, both are season 0/temperate. A trial funded 25 can publish/be received at
Phase 10 on **26**, if publication/access/measurement gates pass. Paid turn
**84** is also season 0/temperate and can use its retained informative evidence
if current bands, access, practice, receipt visibility and treasury permit.
The JSON checks only these transcribed calendar formulas by pure arithmetic;
no world or seed outcome is claimed.

**Payment, physical growth and observation are distinct.** Paid allocation
requires current applicability and treasury (`scientific_claims.py:523`). The
physical kernel additionally checks prerequisites and `0 < p < cap`, scales by
practitioner shortfall/disruption and quantizes (`techniques.py:398–448`). At
`p == cap`, a valid paid allocation adds zero paid-growth term. Allocation
events are first/material split-change notices (`scientific_claims.py:547`),
not a list of every recurring payment; their absence cannot establish absence
of paid use. Saved allocation rows and sparse events must be read separately.

Phase 4 prepares paid effort (`techniques.py:933`); Phase 10 publishes/receives
research evidence (`scientific_research.py:604`). Same-source Phase 10 evidence
cannot rewrite the earlier Phase 4 allocation. Its possible effect begins at
a later qualifying paid turn.

This was source inspection, exact file/Git-blob hashing and pure calendar
arithmetic only. A second source reader reviewed paid-use/evidence/calendar/
phase/growth reasoning. No source/ref/worktree changes, downloads, tests, World
instantiation, native imports/builds/pools or physics ticks occurred. No sampled
outcomes, new eligibility, gate waiver or cadence change is supplied. The
existing controlled proof remains scoped to its actual execution; natural
180-turn occurrence and benefit remain unknown.
