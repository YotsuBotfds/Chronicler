# Optional care through reciprocal retained Kin

This is an inactive source extension from `2f164203`. Health care remains off
for new Worlds. Its legacy `spouse` policy keeps the old five-argument Python
call and exact original Rust preparer. Only an explicit `retained_kin` policy
supplies the new keyword. There is no new CLI, automatic activation or native
persistent field. Native build, Rust tests, full CI, output/RNG parity and
World/checkpoint continuation qualification remain unrun for this candidate.

`HealthCareState.care_policy` accepts `spouse` or `retained_kin`. Ordinary JSON
omits `spouse` through the existing exclusion pattern. A strict getter treats
an actually absent old-pickle field as `spouse`; unknown values refuse.
`set_health_care_policy(world, policy)` requires an already-enabled state and
validates a detached complete candidate before changing only the policy.
Changing it while this turn's work is prepared refuses; an equal-policy call
validates without mutation. It neither enables health nor rewrites episodes,
summary or native work. `care_enabled=False` supplies zero care for both policies.
An old native extension cannot silently downgrade a retained-Kin request.

The extension first completes every original spouse allocation. It then visits
uncared eligible patients in ascending stable-ID order. Each sees at most eight
stored Kin targets, sorted and deduplicated. A donor must have the reverse
recorded Kin edge and be a current live adult rural farmer in the same region,
not travelling, enlisted/excluded, urban, an input patient or already assigned.
A lower-ID uncared patient therefore cannot steal a later patient's spouse.
Parent IDs, names, household membership and sentiment never infer a donor.
Directed FFI operations can record Kin, so a Kin edge is not genealogical proof.
No relationship is created, strengthened or removed.

The optional lookup is a deterministic ordered map of the immediately preceding
eligible worker vector; no pool field changes between those two passes. This
retains exactly the original liveness/exclusion/urban eligibility without new
randomized-hasher construction. Assigned donors are derived from all completed
spouse rows. The fixed scratch array holds eight targets; reverse checks are
bounded by eight stored entries. The new care charge is appended once in patient
ID order after the old sums. Only new donors' existing worker availability is
updated, in the existing worker order. Income/reset/slot-reuse checks, population,
food demand, injury impairment, recovery formula and RNG streams are unchanged.
Enabled lookup/allocation work is additional cost, not a performance gain.

The existing typed experiment request may include `health_care` control
`care_policy`. Legacy omitted requests with saved spouse policy retain their
old control tuple, receipt keys/order and application path. A requested policy
or saved nonlegacy policy appears explicitly in both before/after receipts.
An explicit return to spouse remains an applied setter operation even though
its ordinary state JSON omits that value. Resumed interventions retain the
existing fork, parent-checkpoint and registration validation.

Compatibility is deliberately precise. JSON omission does not establish old
health-enabled Python pickle byte identity: a newly declared default can enter
the model dictionary/pickle metadata. Synthetic owned-model tests cover an old
pickle with the field genuinely absent, same-source policy persistence and
explicit reversion. Native pool/simulator persistence declarations and existing
HealthWork fields are untouched; the one-turn losses remain transient. No
cross-source raw checkpoint identity is claimed. Same-source World continuation
mid-episode and after death/migration/policy change still needs genuine hosted
qualification with fresh native inputs, before any adoption.

The native source regressions exercise the old preparer versus both policies
when no Kin is available; global spouse competition; sorted/deduplicated donor
competition; missing/asymmetric/dead/reused/travelling/enlisted/urban/underage/
injured/wrong-region donors; no parent-only inference; one-time work/income cost,
actual economy production and food demand; pool persistence and next-turn reset;
and FFI rejection before mutation. These Rust regressions are written but unrun.
The bounded Python tests use real state models and fake bridges/metadata only;
they create no World, native runtime, checkpoint decode or live artifact access.
Local guard results and exact source pins are retained externally after the run.
The first local custom guard passed 38 Python parent tests and 97 successful
subtests on Python 3.12.14. These counts do not claim a standard offline guard
or hosted Python 3.13 result. The two new policy modules are registered together
in the offline runner's `health-care-policy` chunk with its unchanged 110-second
limit. A separate source-selection check exercises the runner's actual `--list`
path without running any pytest chunk; native and hosted qualification remain
unrun. The original local test result is retained without an unrelated rerun.
The frozen design is `/tmp/chronicler-retained-kin-care-design-20261029/PLAN.md`,
SHA-256 `a50dc1e033654f138760ad5b1c1d66da69e41fcf64f03f9cfb8202d2b00828b1`.

This changes a care eligibility policy when explicitly selected. More received
care has a caregiver work/income cost. Paired enabled Worlds are needed to
measure recovery, food, survival or welfare effects, including censored patients.
The original full qualification policy and thresholds remain in force; no
scientific, wall/CPU/RSS, default-feature or main-merge result follows from source
or controlled model/pool contracts.
