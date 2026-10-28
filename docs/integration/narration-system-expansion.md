# Narration of the optional system expansion

The narrator reads recorded `TurnSnapshot.health_care`, `.harvest_forecasts`
and `.ritual_gatherings`. The simulation never reads these presentation helpers.
Missing sections in old history remain unknown; the reader does not rebuild
them from final world state. Each section must identify the completed turn
as `source_turn = snapshot.turn - 1`, no later than the narrated moment.

At most one focused line per system enters the existing ten-line standing-state
budget. A moment about these systems reserves room for their lines; unrelated
moments retain the existing state priorities. Every line has an ordinary dated
snapshot fact ID (`work_health`, `gathering`, `harvest_report`, or
`harvest_preparedness`) for passage provenance. Preparation of prompts is a
deterministic read; it makes no LLM calls and does not change event records,
historiographic accounts, attendance, costs or simulation outcomes.

Work-health context reports active temporary work-injury episodes and manual
work/care time in the recorded worker-turn unit. It attributes no individual
diagnosis, clinical cure, avoided death, measured lost grain or monetary loss.
Episode retirement and recovery-work counters are not rewritten as medical
benefit. A section with unknown units is omitted.

Harvest context identifies the assessors' estimate, source, recipient, issuance
and delivery state, and target interval. A pending or withheld report is not
described as delivered knowledge. Future-issued/delivered rows and expired
reports do not enter active context. Intermediate evaluation values never become
a forecast's established future outcome. Granary purchases recorded during a
delivered warning are described as purchases **during** it; their total is not
attributed as excess spending caused by that warning.

Gathering context uses the dated occurrence's frozen host name, actual selected
local attendee count, consumed grain, treasury expense, friendship **attempts**
and capped arrival contact. It makes no organized long-distance pilgrimage or
successful bond-formation claim. Cancellation is described from its recorded
reason; zero expense/exposure is stated only when the receipt records zero.
An off-season snapshot cannot replay a previous occurrence. See the
[gathering contract](ritual-gatherings.md) for its conservative attendance pool.

Fallback labels make the six new event kinds readable. Recurring work-injury
and harvest-assessment bulletins use the existing routine-event folding and
omission counters. Gathering first/change/cancellation events retain their
ordinary importance because the runtime already suppresses unchanged annual
repeats. The older `curator.event_label` used to write persistent accounts is
unchanged.
