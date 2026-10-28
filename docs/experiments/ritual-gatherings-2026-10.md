# Harvest gathering preregistration — 2026-10-28

This registers the first default-off implementation before any outcome study.
It is a synthetic local gathering mechanism, not an empirical reconstruction
of ritual, religion, trust or historical pilgrimage. Constants and attendance
selection are specified in the [runtime contract](../integration/ritual-gatherings.md).
No numerical benefit or runtime overhead has been measured here.

**Unique causal edge:** recurring obligation → actual expense/attendance or
cancellation → additional contact and bounded friendship attempts. There is
no direct generic cultural or well-being multiplier. The existing seasonal
economy, ordinary migration, fixed native relationship capacity and disease
contact are the mediators; none is replaced by a ritual-specific outcome draw.

Freeze source/package/native hashes, mode, world generator, seed list, all
feature settings, thread counts and horizon before comparing arms. Run each
seed from the same feature-enabled pre-occurrence checkpoint. Independent
seeds are the analysis units; connected regions, selected attendees and repeated
occurrences within one seed are not independent replicates. Do not compare
feature-on reports against a default-off baseline without identifying the
intentional behavior change.

| Arm | Additional gathering contact | Gathering bond attempts | Food/funds |
| --- | --- | --- | --- |
| Full | On | On | Charged on actual held occurrences |
| Cost-only | Off | Off | Same rule |
| No-contact | Off | On | Same rule |
| No-bond | On | Off | Same rule |
| Default-off identity | No feature calls/state | None | None |

For an immediate same-checkpoint occurrence, assert identical attendance, costs,
arrival receipts and cancellations in the first four arms before interpreting
later divergence. Over long continuations, downstream differences can change
later eligibility and costs; report those paths instead of claiming perpetual
cost matching. Controls preserve ordinary migration's `people` contact and
the native simulation's independent friendship formation.

Mechanism acceptance requires exact stock/fund receipts, no population change,
no over-budget treasury spend after preceding keep mutations, unspent merchant
commitments, no expenses/exposure/bonds on cancellation, ≤32 actual local adult
IDs, ≤8 disjoint eligible bond attempts and ≤8 contact units per occurrence.
Row order cannot change the selection. Conquest and faith-slot reuse cannot
reset calendar identity. Test turn 7/8/9 and 19/20/21, same-turn re-entry,
save/load and exact native checkpoint continuation. Contact pending inputs must
be empty at each boundary and must not recur on a resumed off-season turn.
Default-off aggregate/native output identity is a separate required gate.

First use small controlled fixtures: food-rich versus shortage/occupation;
no arrivals versus one verified arriving attendee; hostile versus eligible pairs;
full protected native relationship slots versus free space; missing/ambiguous
arrivals; later registry slot reuse. These establish mechanics and possible
pathways, not population-level causal benefit. The implementation unit tests
exercise these controls without a paid model or network.

For an initial **unrun** pilot, use 20 preregistered seeds, 12-region template
worlds and 120 turns (ten calendar opportunities); record both current-default
and an explicitly enabled interacting-system profile. Hold full study and
procedural generator decisions until the pilot establishes that real ceremonies
and cross-region arrivals occur often enough to identify the pathway. Publish
zero-opportunity counts, cancellation reasons, food/funds totals, attempted and
actually retained bonds (read from native state, not the attempt counter),
contact units, disease imports and region shortages. Rare arrivals may make
the contact arm indistinguishable from no-contact; that is a valid null.

Primary mechanism estimands are paired seed-level extra gathering-channel
contact versus no-contact and additional retained attendee friendships versus
no-bond, measured immediately and one resource cycle later. Secondary costs
are treasury depletion, consumed food, changed shortage and disease outcomes.
Do not equate more bonds, contact, or narration with welfare or social cohesion.
Any large downstream benefit must survive the cost-only and pathway-removal
controls and must not be an artefact of larger attendance/opportunity counts.

Nulls: with no verified arrivals, full and no-contact have zero gathering contact;
with no eligible/free relationship pairs, full and no-bond submit no bond ops;
with every occurrence cancelled, all feature-enabled arms have identical zero
expense/exposure; without a contact ledger there is no gathering-channel effect.
Replaying last turn's event, birth origin, proposed travel or final territorial
ownership must not create a new contact or historical record.

Measure overhead only on a quiet host using paired alternating runs and fresh
output directories. Separate ordinary off-season turns, occurrence turns and
serialization/finalization, report population/edge counts, region count and
peak memory, and retain source/host/native identities. The intended work is
O(current agents + current relationship edges + this turn's migrations) once
per occurrence turn, bounded candidate storage per region and at most eight
operations per gathering. The current native graph API exports all edges;
that cost must be measured rather than described as bounded by 32 attendees.
No full-world performance gain, overhead budget, 200-seed gate or feature
promotion is asserted by this preregistration.
