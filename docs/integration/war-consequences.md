# War consequences and dated movement experience (D3)

`--war-consequences` is opt-in, requires the existing health and residence
authorities, and keeps the native migration decision as the sole mover.
Campaigns select combat victims first. The active D3 rule deterministically
releases a declared 30% of those selected victims alive with an injury;
attrition stays lethal. Wounds remove military strength and roster attachment
without booking a death or population casualty. Existing health-care injury
episodes begin after this turn's health settlement and affect the next turn.
The native mortality correction is separately explicit in the service input.
`record_only` keeps all baseline selected deaths and records would-wound rows.

The T−1 separation accessor distinguishes trips, attachment, displacement and
migration. A residence is not an army's field location. New locally witnessed
threat observations are recorded at T before the native tick when a hostile
field army stands at a person's native residence. People currently attached
to an army are excluded from this residence-based sighting. They are not
teleported or prevented from ordinary native migration.

With adaptive livelihoods rules 2 active, a person's own T−1 local threat
adds +0.20 to each adjacent destination's existing native score. This is a
dated motivation to leave, not knowledge that a destination is safe. Actual
departures from a personally witnessed threat are recorded as evacuation
observations; this classification does not prove the added score caused the
move. D3 records the exact witnessed war key and start turn, protecting a later
war that reuses the same key from being mistaken for the original conflict.

Evacuation and living service-release experiences can motivate return toward
the person's own X1 home when adjacent, after a public formal peace for every
personally associated war was recorded on an earlier turn. The +0.15 return
pull decays to zero over 20 turns after that notice. Long active wars retain
the experience under the bounded cap rather than expiring it before peace.
A formal peace notice is not a safety guarantee, and the native decision may
decline return. Continued attachment suppresses the residence-based D3
scores. `record_only` changes no score.

At most 16,384 current threat/return experiences are retained per kind;
deterministic truncation counts are explicit. D3's event history and frame
samples are capped at 256, while injury delivery and exact counters retain
the full current turn. Separation samples also report their full count and
dropped rows. Late demobilization after Phase 10 commits immediately to the
dated event history. Pool replacement drops personal experience rather than
assigning a predecessor's history to a reused stable id.

Focused Python tests exercise campaign-selected death/injury separation,
existing injury authority, late release deduplication, bounded output, dated
local threats, attachment exclusions, exact war-instance peace notices,
observed evacuation/return and memory through a long active war. The lead
integration owner records native score tests, feature-off identity, enabled
transition resume, held screens and browser evidence. These are bounded
contracts, not procedural-world qualification or a guaranteed return policy.
