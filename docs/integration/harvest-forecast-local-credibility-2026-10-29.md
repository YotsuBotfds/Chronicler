# Local credibility for harvest preparedness — source-only pilot

An explicit `preparation_policy="local_credibility"` experiment control lets
past, locally received forecast errors discount later public-granary
preparation. The legacy value is `fixed`; ordinary forecasts and all feature-off
worlds keep that behavior. This extends the reputation/compliance feedback in
the user-supplied Kimi ideation, rather than introducing another hazard draw.

This source starts from `23d4d246`, retaining its optional care implementation.
No native field, persistent native layout, default feature switch, technique,
clock, ecological process or existing RNG stream changes. This is a separate
source-only branch. Genuine enabled Worlds, exact World checkpoint continuation,
default-output identity, full CI, scientific benefit and performance remain
unrun for this new source; parent qualifications retain their original scope.

## Causal boundary

Existing assessors issue and deliver fallible reports. Their observation-count
confidence measures coverage. They already retain production shortfall scores,
but those scores do not influence legacy preparation. The pilot adds:

`delivered assessment → three local production observations → retained error →
later preparation discount → ordinary paid procurement`.

Reports keep their probabilities, confidence, timing, delivery choice, warning
threshold and observation-noise stream. Only the existing desired extra target
is discounted; the existing total-target cap and actual market procurement
remain authoritative. No new grain or cash is created and no purchase is
declared merely because a target rises.

## Local evidence and bounded memory

Only while the pilot is active, a delivered report records the actual present
production/demand ratio at each of its three winter target turns. They are the
same ratios already used by the old evaluation, measuring production with
reserve relief excluded. The forecast observer itself executes in Phase 10,
after Phase 2; this defines the measured quantity rather than a physical
pre-Phase-2 read. Each record keeps its turn. A source score cannot stand in
for those observations.

At resolution the pilot requires the original report and issue/delivery event
identities, actual delivery before the target window, the exact three expected
turns, current recipient ownership, living population, matching owner index/name,
finite measurements and exact outcome/score arithmetic. The report's
chronological `evaluation_sum += ratio` arithmetic is reproduced explicitly;
newer CPython's compensated builtin `sum(float)` is not substituted. Withheld,
unscored, cancelled, incomplete or unreceived reports never become local
knowledge. Global calibration and the global 128-outcome presentation ring are
never consulted for learning or discounting.

Each existing regional `HarvestObserver` retains at most four results. This is
the last four accepted results **across sources and owners at that recipient**,
not four per source. Switching source can therefore evict an older source's
record. Unrelated regions and global report volume cannot evict local memory.
The source identity is an assessor place (`world.regions` index), not an invented
persistent bureau/person identity. A new ruler cannot use the old ruler's
records because eligibility matches both civilization index and name.

Repeated report IDs are inert; conflicting repeats refuse. Source-generated
report IDs encode year/source/recipient, and a report older than the retained
tail cannot be learned again after its ID is evicted. Memory ordering is
validated rather than inferred from display event order.

For a new report, only the same source/recipient-owner results resolved before
that report was issued are eligible. With `n ≤ 4` eligible Brier errors:

`discount = (2 + Σ(1 - error)) / (2 + n)`.

Zero history gives exactly 1. The discount is bounded to `[1/3, 1]`; it is an
action multiplier, not a calibrated probability, forecasting-skill estimate or
validated behavioral parameter. Prior weight 2 and memory cap 4 are frozen
development choices. A false alarm reduces later preparation; a correct later
result can restore it. Less buying can also worsen food security: benefit is
not assumed.

One existing preparation receipt gains the selected policy, discount and at
most four evidence report IDs in pilot mode. It still separately records actual
completed buys/payments. No extra recurring event stream, agent scan or native
getter is added. Production callers build one region-observer index per pass;
memory work is bounded by four entries per relevant region. O(regions + reports)
work and O(regions) persistent storage are structural bounds, not measured
runtime or memory improvements.

## Controls, reversion and persistence

Use an explicit registered expansion-experiment request with feature
`harvest_forecasts` and controls `{"preparation_policy":"local_credibility"}`.
The host forecast/granary/contact system must already be enabled. Existing
`policy` controls (`normal`, `withhold`, `shuffle`) stay independent.

The legacy `CONTROL_FIELDS["harvest_forecasts"] == ("policy",)` tuple and omitted
legacy receipts remain unchanged. Only explicit policy requests or a saved
nonlegacy mode extend before/after receipts with `preparation_policy`; explicit
return to `fixed` is recorded on both sides and actually applied. Existing
retained-Kin controls/ordering retain their semantics. A resumed intervention
still requires an explicit fork and parent metadata.

Changing policy validates the entire candidate before mutation and requires a
pre-tick boundary. Restoration uses the inherited comparison
`math.isclose(current_target, base_target + extra_target, rel_tol=0.0, abs_tol=1e-9)`.
A recorded increment is restored when that comparison passes; targets that
differ beyond the tolerance remain untouched. It clears that restoration record
and retains local memory. Returning
to `fixed` pauses learning and use; reactivation can use retained earlier
knowledge. Same-policy calls are inert, including old pickles lacking the new
field. A mid-target-window pause can leave fewer than three observations, which
cannot subsequently be promoted to a complete result.

Default-valued policy and empty new lists are omitted from model JSON. Declared
fields can still enter new enabled Python pickles; no old/new pickle-byte or
cross-source exact-checkpoint compatibility is claimed. The local memory is
authoritative Python-owned state, not rebuilt from truncated snapshot history.
Existing strict source/native checkpoint admission is unchanged. New native
schema declarations are absent; fresh actual schema tuples remain unmeasured
for this pilot. JSON and owned-model pickle round trips do not qualify World
checkpoint continuation.

The old `expansion_compare` reader explicitly refuses receipts containing this
new policy. It cannot establish matched pre-intervention local knowledge and
must not score these as old forecast arms. A dedicated evidence-aware comparison
and scientific preregistration are later work.

## Focused source checks and remaining gates

The final guarded selection passes 39 parents: 22 exact source-selected new
model/fake cases plus all 17 existing retained-Kin experiment-policy cases.
Their 36 successful unittest subreports are separate. It uses CPython 3.13.5,
with no World construction, native/NumPy/project runtime factory call, child,
network, checkpoint/archive access or blocked attempt. The source-selected
class is byte-linked to its existing registered test module; this is not a
local collection of that whole module or a complete offline/full-suite result.

Checks cover false-alarm/recovery arithmetic, dates and three measurements,
withheld global scores, ownership, source changes, memory eviction/replay,
invalid/nonfinite records, target restoration/idempotence, pre-tick changes,
legacy omissions, explicit reversion, late invalid metadata, model round trips
and shared care-control regressions. All tests remain in existing registered
modules. Their old native owners and existing 110-second offline selections
remain unchanged; the added whole-chunk/runtime cost has not been measured.

Earlier observations remain external and preserved: two guard setup refusals
occurred before collection; the first 21-case selection had two failures; a
later 39-case selection had one old fixture calling a policy change after its
turn had already ticked. Those do not count as passes. The numeric evidence
check and fixture chronology were corrected with the negative source snapshots
retained. Only the final source gets the final 39/36 focused result.

Independent source review, root review, appropriate CI and genuine same-source
checkpoint/default-output proofs precede a separately registered hosted cohort.
No execution activation, horizon/seed change, scientific verdict, performance
claim, default adoption or main promotion follows from these fixtures.
