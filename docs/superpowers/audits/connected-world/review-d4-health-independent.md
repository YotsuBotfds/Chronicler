# Independent D4 review by the public-health lane

Reviewed 2026-11-07 against actual source, the original D4/A4-2 contract,
`docs/integration/war-requisition.md`, the requisition tests and retail-war
interaction tests. This is a source review and focused Python evidence;
integrated native lifecycle, exact resume, feature-off identity, held evidence
and CI remain the lead's integration gates. It is not an approval of an
unreviewed final head or a qualification claim.

Initial reviewed D4 implementation was `82c8976c`, then the recovered lane at
`21483885`. Review found a high-severity lifecycle error: a person recruited
after Phase 2 had already eaten civilian food, but the before-agent-tick army
adapter could consume a second military meal. The lead independently found
the same issue. The correction at integrated commit `fc974452` freezes the
Phase 2 stable-ID service census, uses it for civilian food/work exclusions and
army demand, dates actual consumed meals, and refreshes the native food input
without consuming again. Later recruits first enter military food demand and
civilian exclusions next turn; later releases retain this turn's actual meal.
Focused requisition plus retail-war tests on that stable integrated source:
**51 passed in 1.13 seconds**. A temporary root merge-conflict collection failure
before that run is not counted as a source failure or a passing check.

Reviewed facts:

- Enlisted native people can migrate. The native decision code excludes trips
  and titled carriers, not army roster IDs. The earlier D audit's contrary
  statement is superseded by source and the A6 observed roster migrations.
  Roster attachment, native residence and X1 displacement are distinct.
- Army kits are converted from actual reachable grain withdrawn once; initial
  kits represent real withdrawn carry. The frozen census removes the recruit
  double-meal path. Capacity, commitments and owned/common physical stores are
  handled separately; owned stock is not subtracted from commons a second time.
- Seized titled cargo remains under one custody/terminal-outcome authority;
  restitution is a treasury-funded liability paid through the money seam.
  Payer shortage and recipient ceiling carry do not mint compensation.
- Native enlisted service is keyed by stable ID, sorts/rejects duplicate IDs
  and invalid fractions, keeps residence unchanged, and is a transient excluded
  from native persistence. Slot reuse after death cannot inherit another
  person's army service. Native input is cleared after the tick, cancellation
  and pool-reset paths. Phase 2 supplies the exclusion; current logistics supply
  the actual fed fraction before individual hunger terms run.
- The D3 active rules path deliberately suppresses the pre-existing native
  **whole-polity Soldier-at-war mortality multiplier**, including unrostered
  Soldier occupations. This is the lead's explicit decision under audit D
  section 7.5b, so campaign casualties are the sole war casualty authority.
  Natural mortality remains authoritative. The default-off and record-only
  paths retain the old multiplier. This is an intentional opt-in correction,
  not a claim of default-path identity while the correction is enabled.

The last D4/native source inspection was against root commit `1aa5b8d3`, with
these SHA-256 identities (the lead must re-review any later material change):

| Source | SHA-256 |
| --- | --- |
| `war_requisition.py` | `0368e84903990cc9992dde41db1d7e159e652f6a223467c66fd65dbe21fdf328` |
| `war_requisition_state.py` | `f089a2a058c8bec08bd292ab6501e2388d6ed2f7399b4dc9ebcdb11a8814450f` |
| `enlisted_service.rs` | `2238693fd21f98c242023867d8e9c41a644c8000051eeaecf2e075c6fa90dda0` |
| `tick.rs` | `0655aa3b8d10b28aaf1ac149ce12b5638962be500b8e9c4ebba0d9aab478f02f` |
| `ffi/mod.rs` | `0a076750c3b601d42d3ec889e057e9f62964816fc521080556aac9992eb8d048` |

Remaining limitations are explicit: personal restitution debt lapses at the
creditor's death rather than becoming a new estate claim; closed-claim
retention is bounded at 4,096 and therefore requires a later archival layer
for exhaustive long-run individual accounting; cargo hostility uses dispatch
origin polity. None is described as a named paid military payroll or a second
spendable wealth balance. Source review found no further D4 blocker after the
service-census correction, subject to the final integrated native/CI gates.
