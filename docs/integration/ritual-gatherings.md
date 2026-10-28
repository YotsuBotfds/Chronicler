# Recurring local harvest gatherings

`--ritual-gatherings` is an experimental, default-off hybrid-mode feature.
An explicit enable in another mode is rejected by shared configuration; an
already saved setting is preserved but dormant there. No LLM decides attendance,
cost, cancellation, contact or relationships. This slice implements the
[coordinated-culture roadmap](../superpowers/roadmaps/system-expansion-2026-10.md#3-recurring-gatherings-with-real-attendance).

Every region owns one `harvest:<region-index>` schedule at resource step 8
of the existing twelve-turn seasonal cycle (the end of autumn). It does not
introduce another definition of a year. A schedule survives conquest, a new
host, conversion and native faith-slot recycling. Enabling later starts at
the next boundary; a missed boundary never triggers catch-up occurrences.
Calling twice in a turn cannot spend twice. Saved state retains the next
occurrence and last outcome.

The gathering runs after Phase-10 granary procurement closes its resource
ledger, before the accumulator's keep flush. It reads a fresh native snapshot
at that hook, buckets current adults by region once and selects at most 32
lowest stable agent IDs per region. Children and agents in another region
cannot attend. A birth origin, civ affinity, planned pilgrimage or historical
migration is not evidence of presence. Selection favors older surviving IDs;
the first slice does not model invitations, travel, representative sampling
or an entire region's actual participation.

An occurrence cancels when its legal ruler no longer holds the region,
an enemy occupies it, no adults are present, current food demand/sufficiency
is unmeasured, food is short, uncommitted grain is insufficient, or projected
treasury is insufficient. Cancellation consumes no gathering food/funds,
attempts no bond and queues no gathering exposure. Existing ordinary migration,
trade and disease mechanisms continue independently.

The host must leave two turns of measured resident food demand in market grain,
plus every merchant reservation and pending departure. A held occurrence eats
`0.05 × attendees` grain and spends `1 + ceil(attendees / 16)` treasury units.
These are explicit experimental constants, not calibrated historical estimates.
Grain is terminal consumption; the treasury debit is a recorded hosting expense
for services outside the represented treasury ledger, like existing upkeep.
Neither becomes an imaginary stock, loan or minted cash. Per-occurrence before/
after receipts prove `grain_before = grain_after + food` and
`funds_before = funds_after + funds`. The finance book includes earlier unapplied
keep debits, so several regions cannot spend the same host's remaining money.
Population is untouched. Food costs are additional to the economy's ordinary
eating and are not appended retroactively to its already closed receipt.

Up to eight disjoint attendee pairs can request a symmetric `friend` upsert
through the existing native relationship API. Hostile/negative pairs are
ineligible, a new friendship requires space at both endpoints, and a positive
friendship can only strengthen. Existing kin/marriage records are separate
compound keys and are never rewritten; full endpoints are skipped rather than
evicting an existing bond. The native store preserves a refreshed friendship's
original formation turn. Its void FFI supplies no acknowledgement, so the
record calls these **bond attempts**, never newly formed bonds. Beyond the
native uint16 formation-turn horizon, no bond operations are submitted.

This is a local gathering. It does not dispatch long-distance pilgrims.
Only selected attendees with one unambiguous migration receipt in the current
turn, ending in the actual host region, can add cross-region gathering exposure.
At most eight units enter the existing directed `pilgrims` contact channel,
source → host, without inventing a return trip. A newcomer already generated
ordinary `people` contact; this additional channel represents gathering mixing,
not a second journey. Its existing disease-import consequences remain enabled.
No ledger means no gathering contact. The normal end-of-turn ledger update
consumes and clears pending inputs; no input is carried across a turn boundary
or replayed after a checkpoint.

`RitualGatheringState.contact_enabled` and `.bonds_enabled` are persisted
intervention controls. Set both false for cost-only, only contact false for
no-contact, or only bonds false for no-bond. All arms retain the same calendar,
attendance, food/funds and arrival receipts. There are no generic legitimacy,
spiritual-need, satisfaction, technique or fertility bonuses and no native
memory intents or reserved memory codes.

`snapshot_summary` supplies `source_turn = snapshot.turn - 1`, immutable schedule
IDs, current-turn outcome rows and cumulative compact counters. Rows freeze the
then-host's index/name and attendees' plurality permanent faith ID/name, with
lowest-ID tie breaking. The plurality is descriptive, not an attendance filter
or a faith-owned calendar. Cancellation has no asserted attendee plurality and
no before/after expense balances. A later snapshot without an occurrence has
an empty outcome list. Historical readers must use their recorded snapshot;
absence in an old bundle means unknown, never a reconstruction from final state.

Narration receives only first held occurrences, changed cancellations, recovery,
and changes of host or observed faith plurality. Routine annual attendance and
an unchanged cancellation remain counters and dated outcome rows. Events pass
through ordinary causal provenance; this feature does not manufacture causal
ancestry, accounts or narrator truth.

The [preregistered checks and causal study](../experiments/ritual-gatherings-2026-10.md)
separate mechanism tests from unrun scientific and performance qualification.
