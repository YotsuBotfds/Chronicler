# Public granary purchase observations: pre-registration

Registered on `d051d7c0`, 2026-10-28, before implementation or testing. This
extends the existing default-off transaction-receipt switch with a separate
Phase10 public-purchase domain. No fees, insurance, private sales, voyages,
borrowers, stock/cash arithmetic or random draws are added.

## Frozen mechanism

Observe only successfully committed existing `ReserveFlow(BOUGHT)` entries at
the end of public granary procurement. Record stable civ/region indices and
frozen names, the actual granary keeper and selected source controller, grain
sent/received/transit loss, whole buyer treasury paid, and either the foreign
ruler's credited treasury or the documented domestic-producer sink. Record the
actual demand and source-market price inputs used for that procurement pass.
The pre-procurement projected treasury vector already computed by the existing
kernel plus its actual purchase flows can replay before/after public balances
without another per-receipt scan of the accumulator or agents.

A purchase ID is `(trajectory namespace, public-grain domain, turn, buyer,
destination, source)`. It identifies a committed one-turn public purchase,
never a merchant voyage. The current own/foreign iteration visits a pair once.
Duplicate semantic keys fail closed as incomplete capture; they create no new
financial action. Native mobility and Phase10 procurement keep separate source
turns, phase labels, fingerprints and completeness. Prior saves with no public
frame remain unknown; do not reconstruct old observations from current owners.

Persist only the latest typed public frame/fingerprint and scalar counters,
inside the optional receipt state. Each domain has the existing configured
row cap (default4096, maximum65536). Overflow is explicit and invalidates
completeness, never truncating the authoritative grain flows or changing
procurement. Complete empty means an observed successful procurement pass with
zero purchases; unavailable/not-captured means evidence is absent. Snapshot
rows are detached and carry their own as-of source turn. No lifetime row
history or policy-level transaction list grows over time.

Repeated identical capture is inert. Conflicting same-turn or reversed/future
frames reject before changing the public journal. Exact run checkpoints retain
both domains. Public receipts establish the specified sovereign expenditure or
transfer only; domestic producer payments do not establish private agent cash
balances. Financial eligibility remains false for automatic downstream claims.

## Acceptance controls, before qualification

- Feature off: unchanged WorldState serialization, economic events, treasury,
  grain stocks, granary state, RNG and native payloads on every observed turn.
- Feature on: same per-turn economic/native outputs after excluding only the
  optional observation state/snapshot metadata; no parameter tuning.
- Actual controlled own-market, same-realm and foreign purchases, including
  accumulator projections with preexisting positive/negative keep changes and
  an applied watermark. Buyer debit equals payment; foreign credit equals it;
  domestic sink is explicit. Sent equals received plus recorded transit loss.
- Route suspension, insufficient treasury/surplus and empty markets produce no
  invented purchase. Complete empty, missing economy and unobserved/legacy
  domains remain distinct. Native and public clocks cannot overwrite each other.
- Bounded overflow/duplicate keys, deterministic order, frozen ownership names,
  repeated capture, exact checkpoint resume and an old save with absent public
  fields. No inference of private title or financial entitlement.

Source/docs work may proceed during the reserved quiet benchmark; all tests
wait for its completion signal. A focused passing slice is not a full run gate
or qualification of metrology/insurance.
