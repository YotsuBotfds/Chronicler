# Local movement branches abroad

`--movement-branches` is D1c, opt-in and off by default. It requires hybrid
agents and agent movements. Mode `funded` supports native membership;
`record_only` observes without paying or acting, and `cost_only` pays the same
fees without supporting membership. The mode is fixed across exact resume;
the feature may be explicitly ended. Guild movements remain tied to their
city and use D1b guild leagues for cross-border organization.

The Phase 10 writer counts people already abroad by native `movement_id`
(Python movement index + 1), physical region and the region's controller.
Living adults age 16 and older, excluding merchant trips, organize locally.
A branch is identified by its movement and host polity, with a stable,
checkpointed, never-reused integer id. At most 256 lifetime identities are
kept. New identities beyond that bound are refused and counted; old identities
are retained through dormancy, movement end, death and migration.

Up to 32 members per branch, and 512 across the whole turn, in stable-id
order, pay 10 milli each from their actual one spendable wealth balance.
At least three must be able to pay before any is charged. This is a local
license/service contribution to the host treasury for meeting and petition
facilities. Money goes through `money.pay`, collection purpose `branch_dues`,
native alias `remittance`, disjoint batch `0xD1C000 + branch id`. Its treasury
sub-unit carry is explicit and closes with the collection. There is no branch
cash account and no additional minted wealth. Constants are declared modeling
choices; no held outcomes were used to tune them.

A successful payment in Phase 10 T makes native organizational permission
available at T+1. The reader requires its consumer's own turn and exactly the
T−1 frame, refusing same-turn/future data and treating stale/missing data as
unobserved. Public hostility and C1 trade closures between home and host block
funding and delivery, in either direction. C1's unchanged legacy multiplier
does not create a journey closure. No residence-ledger internals or provenance
are read. Members know their own movement and organize where they already
live; this does not deliver home-country news across a closed border.

Native permission only removes the extra 0.10 abroad lapse and allows the
existing recruitment rule to consider that host. Adult, local co-residence,
settlement/bond exposure, personal grievance, satisfaction, transported news
and the other lapse conditions retain their existing authorities. No need,
grievance or influence credit is stacked on top. A funded receipt is evidence
of a local payment and permission available next turn, not proof that a
specific recruit or retained member was caused by the branch.

The native input has explicit source and target turns, validates the complete
batch before mutation, refuses overwrite of an unconsumed input, and is
consumed once. A failed tick releases a same-turn pending input. Transient
native fields are absent from both payload and checkpoint schema; Python
rebuilds them from its dated state after exact restore. A rebuilt legacy pool
clears old payer ids while preserving branch identities. Records distinguish
absent, unobserved, measured zero, non-paying observations, funded/cost-only
payments, poverty, capacity, hostility, closure and movement end.

Validation includes real money-seam contract tests, the native pass's lapse,
recruitment and checkpoint-layout regressions, and active native exact resume.
Constructed transitions are identified as constructed; they are not natural
activation or efficacy evidence. No default promotion, full 200-seed screen or
procedural qualification is implied.
