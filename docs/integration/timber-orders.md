# Timber orders (Connected World A4-3)

`--timber-orders` is default off and hybrid only, requiring `--timber-supply`
and `--local-budgets`. It adds no native state, balance or mortality authority.
The named merchant's existing wealth pays the origin ruler for real commons
timber; the destination ruler funds a real, separate order escrow from treasury.
Escrow never belongs to the merchant's spendable balance before delivery.

Only fresh PL1 repair needs refused for `no_forest`, `too_far`, `forest_depleted`
or `forest_busy` can order. The refused gap already excludes local stores and
PL1 cargo; A4-3 subtracts its own expected live deliveries as well. Each order
uses uncommitted stock, excluding the origin's repair need and earmarked store.
Reach follows the actual merchant graph, including diplomatic, blockade and
quarantine closures. Origins and destinations can have different rulers.

The purchase price is the origin's most recent positive raw-material plan
price from an earlier completed turn, with the ruler's most recent regional
price as fallback. Unknown prices refuse purchase; no invented fallback price.
The order unit price is `ceil(plan_price / 0.99^hops * (1 + 0.10*hops))` in
milli-coins per timber unit. Physical loss is a declared deterministic 1% per
hop plus the graph's sea-raid risk fraction; these are separate model losses,
not claims that a discrete native raid was observed. Budget and merchant cash
reduce the divisible quantity before dispatch. The narrowest merchant route
capacity bounds each cargo; at most 64 live orders, 32 closed rows and 256
frame events are retained, with dropped-event counts.

A dedicated L9 provider `timber_orders` belongs to the existing `repairs` group.
Its finite envelope promises **escrow-funded timber dispatch**, not instantaneous
physical delivery. Dispatch runs in `phase10_before_reserves` after PL1 prepares
its fresh needs and before L9 settles the envelope. Money is removed from the
destination treasury once, in whole coins, and held in the order's explicit
`escrow` cash account. The merchant buys the timber once through the shared
payment seam; free stock is removed once, and cargo carries title outside every
regional stockpile. Each order has a monotone persisted id, a dated price and
one holder; a holder cannot carry two orders. A live titled-food carrier is
excluded, as are trips, enlistment and existing work reservations.

At the start of every carried turn the merchant reserves its whole turn in the
existing native trade work registry. Its ordinary modeled merchant income is
withheld through the shared paid-work receipt and recorded. This replaces that
income with the actual procurement margin. It does not add a second income.
At most one hop moves per turn, and nothing moves on its dispatch turn.

Delivery transfers physical timber into the **existing PL1 repair store**,
using `deliver_ordered_store` to include it in PL1's opening/delivered/closing
account. No new parallel timber store exists. Only delivered milli-timber earns
an escrow payment to the merchant. All unearned or wealth-ceiling-refused cash
returns to the original destination payer, including its sub-coin treasury
carry in the package's money book. It is never minted, silently rounded away,
or redirected to a new controller. A terminal order holds neither cargo nor
escrow. Every transition checks both:

```
opening cargo = aboard + delivered + physical losses + deposited
funded escrow = held cash + merchant credits + payer refunds
```

A lost/closed route, controller loss, expired order (12 turns), released/dead
carrier, pool rebuild or explicit switch-off cancels delivery. Remaining timber
is deposited as real commons stock where the order currently stands; the
merchant bears this recorded procurement loss and the destination gets its
escrow back. This is an intentional adverse outcome, not a teleport back or an
unrecorded return sale. Pool rebuilds release saved holder bindings before ids
can name other people. With D4 enabled, an actual hostile army under war pressure
can seize the timber: it remains timber in local commons, never army food.
D4 receives the original-cost value of the surviving quantity as a restitution
claim against the actual actor; the order closes once and refunds its customer.

The standalone tests cover both balance identities, whole-bill rejection before
mutation, finite envelope division, store-only delivery, ceiling refunds,
route loss, pool-reset release, checkpointed escrow/id preservation, committed
stock protection, dated-price refusal, net-of-transit demand and non-food war
seizure liability. Natural-world activation, exact enabled resume, held evidence
and browser/scale checks must be recorded against the integrated source; these
tests do not establish qualification.

With active A6 rules 2, dispatch uses the same canonical dated personal market
information gate as titled food trade. An unknown destination cannot consume
stock, merchant money or treasury escrow. A surviving carrier's own terminal
cargo outcome is recorded with `package: timber_orders`; a route failure,
recipient loss, release, expiry or seizure discourages that person's next
order to that destination over A6's declared experience window. The recorded
outcome remains the actual timber outcome: a local commons deposit is never
renamed a return to the original owner. Record-only and rules 1 preserve the
previous dispatch decisions. Completed delivery still controls physical store
credit and actual payment independently of these choice inputs.

Current dated B3 public-work timber refusals join the existing PL1 RS2 refusal demand; their incremental gaps are combined by destination before in-flight timber is subtracted once. Origin public-work needs are protected from export along with ordinary repair needs and merchant commitments. An actual arrival is also subtracted from PL1's earlier same-turn gap through the later L9 decision, avoiding immediate duplicate procurement. Those uncapped per-region turn receipts are private and excluded from checkpoints; the physical store and closed order remain the durable facts. Seller and destination payer must be different current controllers. Disabled or stale B3 observations supply no demand.
