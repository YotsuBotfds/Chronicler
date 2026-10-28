# Prospective finite research agendas: source audit and proposed contract

Status: **design for internal review, no recurrent runtime implemented**.
The audited source is `b25727e36eb47513a6bd7b3209f15de9c14463c3`. Existing
single-cohort defaults, publication rules, old studies and native evidence
remain unchanged. This registers implementation semantics before implementation;
it does not register or qualify a natural-world experiment.

## What the current source actually permits

`scientific_claims.py` creates claims only when `state.claims` is empty
(406–425), using the two fixed `RECIPES` (22). For each claim it funds one
original when none exists (429–433), then refuses further replication once
any trial for that claim has `parent >= 0` (434–443). Those predicates do not
retry failed, cancelled, withheld or null trials. No production path clears
the claims or advances a research generation. Thus the ordinary pilot creates
at most **two claims, four paid trials and eight trial treasury units**, even
after many context changes or academy foundings. Its six-turn paid adoption
can continue; the research ceiling does not mean the entire feature stops.

The declared 20 claims / 40 trials are storage ceilings, not currently an
ongoing scheduler. Trial IDs are `len(state.trials)` (202); original claims
use recipe enumeration IDs (411). Parent, receipt and message links use these
integer identities and directly resolve retained records (234,268,363–371).
Clearing/reusing lists can misassociate old work or orphan pending delivery.
Scholarship institutions also append permanent seat indexes (scholarship.py:
764–771); a replacement academy is not its predecessor.

`state.cohort` is **not unused**: measurement noise reads its current value at
publication (297–298). Incrementing it while an old paid trial is pending
changes that trial's observation. This design never changes that measurement
namespace. `started_turn` also stays fixed: it anchors the existing six-turn
effort cadence (508–509), not a replaceable research generation.

Naively adding new copies of a proposition is unsafe. Dependence groups
contain `claim.id` (221,251), so new IDs for the same question can inflate
group accounting. Policy constructs recipe-keyed shares but iterates claims
again to emit rows (526–548); duplicate applicable recipe claims can distort
allocation. The current summary finally slices belief rows to forty (606),
which cannot silently discard later academies' policy rows when more topics
exist. These are required design boundaries, not optimization opportunities.

## First extension: exact retained records, finite recurrence

Use an explicitly enabled, legacy-omitted `research_agendas` substate. Absent
or missing on an old checkpoint means the exact existing single-cohort path.
No empty agenda object, new summary key, RNG draw or control receipt field is
materialized on that path. Safe missing-field access must also handle older
enabled Pydantic checkpoint objects, not only reparsed JSON.
Merely adding default-None Fields or PrivateAttrs is insufficient: it changes
new disabled objects' raw dictionaries/pickle even when JSON omits the field.
Research state and proposal/message agenda metadata therefore require truly
lazy storage, attached only on opt-in, with nested validation/serialization,
deepcopy and experiment-control roundtrips preserving it. Compare disabled raw
serialized bytes against frozen old source, not only model equality or JSON.
Absent legacy data remains legacy. A present null, incomplete or malformed
agenda payload/backing value is an error, never an implicit reset or fallback.
Enabled correctness uses complete serialized/byte comparisons because ordinary
Pydantic equality can ignore undeclared lazy keys. Serialization exclusions,
modes and validation context must be honored without mutating caller input.

Keep the existing record ceilings: **20 canonical topics, 40 paid trials,
20 lifetime-enrolled academy seat IDs, 400 proposal receipts, 800 evidence
receipts and 1,200 pending messages**. Retain every accepted raw record, cost,
source, group, date and reference; there is no compaction or raw eviction.
Add at most **ten agenda-cycle records**, including the adopted pilot cycle
zero. This admits meaningful repeated paid research in several contexts and
institutions, rather than promising unlimited research at finite capacity.

After capacity is exhausted, stop new research before payment/evaluation and
report the actual blocked capacity. Finish already-paid work, deliver or
expire pending messages normally, retain old knowledge and continue ordinary
eligible adoption. Full/failed/cancelled/withheld/null records are never
selectively removed to buy a favorable retry. Closed agenda means closed to
new funding, not forgotten evidence. These are bounded rows and per-turn
work, not a promise that exact integer counters or the world timeline occupy
constant bytes forever. Unlimited research with addressable raw evidence is
a separate archive-persistence project.

### Identity and canonical questions

Claim and trial IDs remain append-only unique integers; no record is deleted
to reclaim an ID. The existing `cohort` measurement namespace is never changed.
An agenda has a separate stable cycle ID, actual opening/closing dates,
immutable origin/participant seat IDs, canonical claim IDs and paid trial-ID
membership. Cycle zero denotes the retained original pilot; it does not
invent dates that old data did not record.

The canonical topic key is the full registered proposition: recipe, complete
ClaimContext (including crop, crew and protocol), metric, threshold,
comparator/intervention levels and horizon. Origin, cycle ID and publication
date are not part of scientific equivalence. A new agenda reuses an existing
claim ID for an identical key. A novel context allocates new immutable topics
for irrigation and masonry. First proposition origin/date/event stay fixed.
No new physical truth label or beneficial-recipe filter is introduced.

Every new agenda has its own dated announcement event. A renewed question is
not a fresh evidence unit. Proposal receipts/messages carry a legacy-omitted
agenda ID so renewal deduplication and expiry use the actual agenda
announcement, rather than pretending the original topic was proposed again
or reviving its expired broadcast. Evidence still references its unique paid
trial and actual resolution. Funding cites the canonical proposition plus
the actual agenda announcement, and replication cites original funding.
Original/replication selection is scoped to that agenda's trial membership;
an older cycle's trials cannot suppress or become the parent of a new cycle's
replication. A replicating academy must actually receive that agenda's dated
question; an old question receipt alone does not authorize new-cycle funding.
Proposal known/delivery/relay keys include `(agenda, canonical claim, recipient)`;
evidence keys remain `(seat, global trial)`. Never relabel an old proposal
receipt or message as a later announcement, nor renew its sent/received/expiry
dates merely because the canonical question matches.
An identical topic can be renewed by another academy after the first proposer
falls. Fund originals from the actual agenda origin, not the immutable claim's
historical origin; retain the first claim ID/date/event and historical payer.

Canonical claim reuse keeps same-topic source deduplication and within-block
group means across cycles. A second alias of the same recorded source adds
no evidence. Distinct observations in the same declared environmental block
share one capped policy unit. A new cycle, academy or calendar year does not
certify independence; the existing Markov climate/shared evaluator limitations
remain explicit. Different contexts are not pooled as universal evidence.

### Scheduling and actual work

At most one agenda is open for funding. Its funding window is actual source
ages **0–23**: originals may first fund at ages **0–11**, and a replication
may fund only after its own original's actual funding plus the existing
12-turn lag, through age 23. Normal publication may therefore occur at age
24. Unfilled slots close as unfunded opportunities with their reason; they
are not fabricated failed trials and incur no cost.

The earliest next opening is **25 turns after actual opening**. The extra
turn both separates the funding window from the next opening and avoids
phase-locking every question to one season of the 12-turn calendar. This is
a prospective scheduling choice from source constraints, not outcome tuning.
Without eligibility delays, opening season-step is `(initial + cycle) % 12`,
so the ten finite cycles span all four seasons rather than one locked phase.
Eligibility delays use actual dates. A dormant host resuming after many
missed openings creates at most one actual new agenda, with no backfilled
payments, proposals, measurements or claimed historical cycles.

Choose the next eligible origin deterministically by a persisted round-robin
cursor over enrolled stable seat IDs; wrap when needed. Do not inspect
support, confidence, hidden physical treatment benefit or previous success
to choose the next origin/context. Eligible means the existing living
academy, current owner/population/grain, sedentary/current local practice and
context rules. Academies founded later may enroll and originate research
until the existing twenty lifetime seat slots are full. Fallen IDs are never
recycled; once that cap is full, additional academy admission is explicitly
unavailable. Expanding or rotating that roster is not part of this first
finite extension.

Freeze each agenda's living enrolled academy participants at its actual
opening (at most twenty); context/practice need only match when funding or
using evidence, not when receiving a question. They alone receive that agenda's
question broadcasts and trial results. A newly founded academy is a new seat; it gains no old receipts
by sharing a region/name/owner. It may formulate the same canonical question
in its own agenda, but old results require actual institutional delivery.
An already-sent message can arrive after its sender falls, as today; a fallen
sender cannot create a new relay. Replacement seats never receive messages
addressed to their predecessors.

This first extension is explicitly closed-cohort dissemination. Renewing a
canonical question refreshes only its question announcement, not old results'
publication date, six-turn lifetime or recipient set. Old archived evidence is
not rebroadcast to a later cycle or newly founded academy. After expiry it
remains local retained knowledge for its actual recipients; a later academy
needs new actual trial/result receipts. A durable archive lending/republication
system would require a separate dated authorization and evidence-age contract.
Adopted legacy cycle zero is an explicit exception to the new frozen-roster
assertion: its pre-existing dynamically enrolled recipients and pending paid
work retain ordinary legacy delivery semantics until actual result expiry.
Its unknown historical opening roster must not be reconstructed as frozen.

Before opening, reserve capacity for up to four paid trials, the zero or two
new topics, two proposal receipts per participant and four evidence receipts
per participant. Include any existing reservations and pending messages in
the check. These bounds give at most 400 proposals and 800 evidence receipts
over ten cycles. Release unused reservations on closure without deleting
records or changing money totals. No ordinary debit/evaluation happens before
its record capacity is available.
For adopted legacy work with unknown historical opening recipients, reserve
against the full twenty possible enrolled recipients, not an invented smaller
frozen opening roster.

Every actual trial still costs two projected treasury units with floor twenty;
ordinary academy upkeep and accumulator `keep` semantics remain. Evaluation
uses the existing hypothetical four-worker comparator plot, not spawned
workers, a second harvest ledger or claimed real labor allocation. The fee
buys the already documented research service. Changing actual researcher
labor allocation would require its own production/opportunity-cost contract.
Measurement noise, physical functions, thresholds, withholding, transmission
and sham controls remain fixed. Publication v1/v2 is an independent explicit
choice, with no automatic upgrade to favor completion.

### Old knowledge, policy and snapshots

Current policy selects at most one known canonical topic per recipe matching
the academy's actual current context. It reads all actually received eligible
evidence for that topic across retained cycles. A→B→A returns A's previous
knowledge without a replacement measurement; inapplicability does not delete
an archive. Repeating a question cannot create another policy vote.

Preserve the existing one-payment-per-region, one treasury unit and total
allowance at most .01 on the original persisted six-turn cadence. Multiple
cycles cannot stack payments or grants. Per-turn allocation rows remain at
most two recipes per enrolled academy (forty total). Current policy belief
rows use the same canonical current-context selector, so forty is a proven
bound, not a truncation. Archived questions remain separately addressable;
absence of a current-context row cannot be described as forgetting.
Respect production phase order: source-turn Phase 10 publication/delivery can
change the end-turn confidence row but cannot alter that same source's earlier
Phase 4 payment/share. Allocation rows retain the confidence actually used.

The preserved six-turn payment cadence has a structural exposure limit:
`started_turn + 6k` samples only two of the four three-turn seasons in a
twelve-turn year. Twenty-five-turn research openings can span all four seasons,
but topics in the other two seasons never have an eligible paid-use tick under
this cadence. Retain and report those trials/archives without calling their
missing paid use an efficacy null. This design does not claim four-season
economic use or change the cadence to favor coverage.

Opt-in summaries disclose agenda mode/current cycle, actual funding deadlines,
closed/unfunded slots, capacity reservations/usage/blocked reasons, retained
archive counts and completeness. Full retained topic records remain available;
dated `trials_resolved` still contains only that source turn's actual terminal
rows. New-cycle/proposal/funding/receipt/allocation events use the ordinary
simS→snapshotS+1 clock. No final-world fallback fills a missing dated archive.
Observers/viewer must recognize the new mode before calling its new schema
complete; historical single-cohort summaries remain byte compatible.
Strict comparisons must match research mode, scheduling/reservation rules and
actual agenda lineage across arms; an unknown or mismatched agenda mode is a
blocker, not an ignored extra field. Legacy control receipts/flags stay
unchanged when no agenda state is present.

### Accounting and activation boundaries

For every source turn, trial-expense increment is twice actual newly funded
trials; lifetime trial expense is the sum of every retained paid trial cost,
including failure/cancellation/withholding/null output. Effort-expense
increment is the sum of actual allocation-row `paid`, once per paid seat.
Opening/closing/reserving an agenda changes neither expense nor treasury.
Routine allocation events remain thresholded and cannot reconstruct lifetime
expense; snapshots/counters remain the money record.

An explicit opt-in on an existing pilot prospectively closes its old funding
schedule at the activation date, retaining all previous and already-paid work,
messages and observations. It records their legacy cycle membership without
rewriting status/date/cost; the first new agenda is no earlier than activation
plus 25. Reject an inconsistent unsupported archive before mutating it. A
fresh empty opt-in world opens cycle zero at its first eligible actual turn.
`started_turn` is assigned only as it was for the first pilot and never reset.
Mark an adopted cycle explicitly as legacy, with historical opening-roster and
deadline completeness unavailable. The legacy source permits arbitrarily late
first funding and later academy enrollment; its records cannot be retrospectively
judged against new age-0–23 funding windows or participant-at-opening rules.
Only the prospective activation close is a new scheduling intervention.

A research-specific pause stops new trial funding and new agenda creation but
retains the opt-in substate and uses its archive-aware selectors, publication,
delivery and paid adoption. It must not fall through to the legacy scheduler
or clear state. Resume uses actual dates and does not replay missed agendas.
The existing whole-feature removal behavior is separate from this
archive-preserving research pause.

## Counterexample acceptance matrix before runtime integration

| Counterexample | Required opt-in outcome |
| --- | --- |
| Renew same context/question in cycles 0 and 1 | Same canonical claim IDs; new stable paid trial IDs; no duplicate recipe vote. |
| New context at another/new academy | New immutable contextual topics when capacity permits; actual source dates and payer. |
| Renew the same canonical topic after its first origin falls | Fund from a different current agenda origin; retain first topic ID/date/event unchanged. |
| Same source alias is received in a later cycle | No added group/weight or confidence increase. |
| Two contradictory readings share a block across cycles | One total policy unit with its ordinary within-block mean. |
| Context A→B→A while A's archive is positive | Old A confidence returns; no list reset, reroll or replacement receipt. |
| Old trial is running or host dormant when a cycle changes | Original measured outputs/noise/source/namespace remain unchanged; actual late resolution anchors delivery. |
| Old message is pending at closure or after sender fall | Original unique trial/recipient receives it or explicit ordinary expiry; never a new record. |
| Fallen academy and new seat in the same region | No inherited receipt, original trial completion or misdirected message. |
| Twenty topics / forty trials / ten cycles / reserved capacity full | Explicit reason before debit/evaluation; old data and policy remain usable. |
| Archive contains failed/cancelled/withheld/null trials | Every paid cost and terminal status stays retained; no selective retry slot. |
| Multiple current and archived contexts exist for both recipes | At most forty current belief/allocation rows, no clipping or duplicated grant. |
| Cohorts begin from each of four season origins | Actual 25-turn openings rotate season steps; no absolute-calendar effort regression. |
| A researched season is outside the two paid-use phases | Archived/current confidence may exist, but no eligible allowance is claimed or invented. |
| Partial original funding and deadline expiry | Exact costs, explicit unfunded slots, no fictitious trial or refund. |
| Adopt a legacy pilot with late originals or later academy enrollment | Preserve valid old funding/delivery; legacy opening roster/deadlines remain unknown, not fabricated new-window violations. |
| Same tick is called twice around open/close/delivery | No second event, payment, admission, measurement or cycle. |
| New receipt arrives in Phase 10 of a paid turn | End-turn confidence can change; earlier Phase 4 payment/confidence/shares stay unchanged. |
| Save before/after opening, funding, closure and pending delivery | Exact enabled continuation across state/history/events/native/common outputs. |
| Research pause/resume on a populated archive | Retain metadata/knowledge; no legacy fallthrough, backfill or repeated payment. |
| Recurrence absent, including old JSON and Pydantic pickle | Existing source serialization/RNG/outputs remain identical without stripping fields. |

The companion `tests/test_scientific_research_lifecycle_audit.py` describes
three mechanical counterexamples in the audited legacy source: the four-trial
ceiling despite a later academy/context returns, failed work consuming those
same slots, and the live measurement effect of manually changing `cohort`.
After a host CPU slot was released, the three original focused checks passed
under the offline guard. A subsequent prospective review added the explicit
season/payment coverage counterexample before runtime edits. These are
eight passing checks in 0.40 seconds, with no native modules, blocked I/O or
oracle runtime calls. They describe audited legacy/calendar behavior, not implemented recurrence.
The acceptance matrix above must become meaningful opt-in tests after internal
design review.

No runtime/model/CLI implementation, gate, world cohort, parameter fit,
promotion or default change is included. The immediate review question is
whether this finite retained-record contract is coherent; a durable external
archive and unlimited chronology remain roadmap work.
