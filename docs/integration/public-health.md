# Connected public health (C2b/c, crowding and C4)

`--public-health` is experimental and off by default. It requires hybrid agents,
epidemic care, local budgets (through care), infrastructure condition, the residence
ledger and quarantine rules in `closure` or `cost_only` mode. No new mortality
authority or native field is introduced.

With adaptive livelihoods rules 2 enabled, a new care or border-guard offer
consults that person's dated work experience after excluding existing labour
holders and resolving a positive feasible share. Refusing an offer never ends
an existing commitment. Full untruncated personal wage receipts and attributable
native paid-work income costs are recorded as `epidemic_care` or `border_guard`
experience before the turn plan is dropped. A mixed paid-work share has unknown
personal cost; forgone owned-harvest title is also unknown where the retail pilot
could supply one. Neither is replaced with an invented zero. A refused wage bill
installs no paid share and records zero service payment and service-withheld
income, while the actual lost farm time remains in its existing receipt.

The single L9 care envelope now includes the expected ration value alongside
wages. The named carer plan reserves both, and after wages it buys at most the
remaining gross envelope value. One patient ration is the existing per-capita
food amount. Grain must exist in the local or directly adjacent open region,
after native commitments and household titles. The dated previous market price
is required; missing prices mean no purchase. Foreign public grain is paid to its
actual controller through `money.pay`, purpose `care_supply`, before consumption.
Local grain belongs to the paying ruler already: it is an internal allocation,
recorded at its gross value without a self-payment or a fictitious cash sink.
L9 settlement reports actual fiscal spending, while receipts expose the internal
food opportunity cost separately. Missing food limits next-tick capacity and
records the paid carer time that cannot supply patients. Food is never credited
again to household consumption.

Phase 10 dates actual active irrigation service for the next epidemic tick.
Irrigation is a declared water-management proxy, not a claim that the model has
waterworks or sanitation buildings. Its full service reduces within-region flux
susceptibility by 20%; no other pathogen, endemic severity, injury episode or
death path changes. Missing or stale service is neutral. The epidemic tick reads
X1 aggregates through `read_frame(consumer_turn=T)` only: the frame dated T−1.
The displaced share adds at most 25% susceptibility, keeping the existing density
term. Unobserved residence is labelled, never inferred from narration's share.

C4 issues reports from reported regional outbreak rows. Own reports arrive after
one turn; neighboring ledger recipients after two, plus
`--public-health-report-delay` (0..20). Reports expire five turns after delivery.
Stable report IDs survive checkpoints. Decisions select the latest delivered
source/pathogen report, preserving its prevalence and target at issuance. The
current tick's own observed deaths and infectious person-turns enter memory only
after decisions, so the policy uses prior own observed fatality. Without that
experience it records uncertainty and keeps borders open.

The explicit policy loss function values expected imported mortality at 100
treasury units per death, against enforcement, route and goods-contact costs.
Only trade, and migration when the existing quarantine channels include it,
enter preventable contact. Soldier and pilgrim contact never becomes a claimed
benefit. Food imports by foreign origin are not presently recorded, so the cost
uses a labelled goods-contact proxy; it must not be described as measured food
imports. `--public-health-policy shuffled` rotates reported prevalence between
same-pathogen source regions before delivery, preserving report recipients,
delays and random streams. When there is one source the shuffle has no contrast.
Quarantine's existing affordability and stability conditions remain authoritative.

Named border guards replace the anonymous flat enforcement charge while this
package is on. One guard-equivalent per advised directed civilization pair is
funded from the same finite L9 care envelope; it can be proposed without an own
outbreak. The care planner reserves the guard wage share first. Eligible adult
farmers at own customs regions on ledger edges to that target are selected by
stable region then stable person ID, excluding every already booked worker,
patient, army member and traveller. Work removes their actual farm-time share;
`money.pay` pays `guard_wage` (500 milli per worker-turn), and native paid work
withholds the matching ordinary income. A team that is partial, unpaid or ceiling
limited provides no closure capacity. Its lost labour is still recorded.

The route snapshot precedes Phase 2 work planning, so guards of T staff closures
at T+1 only. Phase 1 consumes only capacity dated T−1. Current delivered advice
still plans teams before the first closure is possible; there is no bootstrap
from unstaffed declarations. Quarantine `cost_only` names and pays the same teams
but its original channel guards close no route. Exact checkpoints retain guard
IDs, wage books and dated staffing; an inexact pool reset clears id-bound teams
and their closure capacity. Guard wages, withheld income and patient-ration cash
are separate A1 ledger channels rather than invented household credits.

`--public-health-mode cost_only` keeps wages, real supplies, reports and
displacement crowding, suppressing the care CFR and sanitation effects.
`--epidemic-care-mode cost_only` still suppresses care independently. Existing
quarantine `closure`/`cost_only` remains a separate restriction control. These
switches make the arms explicit rather than silently overriding their channels.

Receipts retain source dates, sellers, internal value, actual cash, consumed
grain, refused purchases, missing observations and the exact report IDs used by
each decision. The viewer keeps absent, malformed, unobserved and recorded zero
distinct. No paid narration is used. Quantitative effects are unqualified until
the registered held screen runs; declared constants have not been tuned on held
outcomes.
