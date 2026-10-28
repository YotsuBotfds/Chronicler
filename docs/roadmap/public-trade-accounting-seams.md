# Public trade accounting: next-slice audit

Read-only audit on receipt source `442f0b07`, native crate tree
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`, 2026-10-28. This does not include
subsequent merchant-tax branch changes. The receipt foundation remains
observation-only. No fee, insurance policy or private cash account is activated.

## What the current code actually settles

| Existing seam | Quantity/title boundary | Cash boundary | Consequence for a new system |
| --- | --- | --- | --- |
| Native merchant reservation/departure | Shared regional stock reserved; a departure debit is queued | No per-merchant purchase payment | Stable custodian/voyage IDs do not establish an owner, buyer or borrower |
| Native merchant arrival | Gross arrival queued; following goods economy applies transit decay | Delivered margins are aggregated per source region and divided by merchant count | Not a private sale receipt or per-voyage settlement |
| Native merchant wealth | Regional `merchant_trade_income` is added to an individual wealth score, then decayed/capped | No matching private purchaser account is debited at that operation | Do not treat the wealth score as a closed cash ledger |
| Public granary purchase within the realm | Real source grain debited; received grain credited to the ruler's granary | Buyer's treasury spent; the documented counterparty is the realm's producers, not an explicit native agent cash account | Honest public expenditure with an explicit unmodeled-producer sink; not private producer settlement |
| Public granary foreign purchase | Same real grain boundary, with explicit sent/received/transit-loss values | `finance.transfer(buyer, seller, cost)` debits/credits actual public treasuries; finance can additionally move specie | Strongest existing closed public-cash seam |
| Maritime piracy | Existing sea-crossing loss is observed; public piracy measurement is consumed later | A separate abstract treasury loss is assessed against the then-observed origin ruler | A second public consequence, not proof that ruler owned or insured merchant cargo |
| Treasury trade tax | Native economy derives a tax base; Python applies whole tax with fractional carry | Macro treasury credit, rather than a per-sale double-entry transaction | Do not join it to one receipt and infer that merchant paid a matching cash amount |

Source anchors: native `economy.rs:1653` (delivered margin/income) and
`tick.rs:1339` (merchant wealth); Python `grain_reserves.py:551` (purchase),
`finance.py:526` (public transfer), `simulation.py:1799` (tax carry), and
`maritime.py:1306`/`:551` (measurement and public piracy spending). These line
references describe this audited source, not a later branch.

Native delivery-buffer arrivals retain source/destination/good/quantity but no
merchant/voyage identity. The receipt's gross arrival cannot establish a final
cash sale by matching a later aggregate or per-log ordinal. A buffer can also
survive a failed economy tick. Later settlement tracking must carry an explicit
identity through that actual success boundary, or remain aggregate and say so.

## Readiness

**Ready for a separately reviewed small slice: public procurement receipts.**
Existing `ReserveFlow(BOUGHT)` already records buyer, seller, source,
destination, sent/received quantity and actual whole payment at the operation
that changes both goods and public cash. Add only a stable purchase ID and
bounded observation/export contract first. One committed public purchase is a
transaction; it is not a multi-turn merchant voyage. Current iteration visits a
source/destination pair at most once in its eligible own/foreign pass, so a
semantic `(trajectory, turn, buyer, destination, source, grain)` key can be
validated for uniqueness. Fail closed if future planning introduces duplicate
keys. Preserve the original untruncated financial flows; cap only derived
observations, with explicit overflow. No native pool identity is needed for
this public-civ/region journal.

**Dependency blocked: grain inspection fees on merchant receipts.** There is
no established private cash payer or legal cargo owner at the receipt boundary.
A public cross-border procurement levy could instead name the buying ruler as
payer and selling ruler as receiver, cap the combined purchase+levy against the
same projected treasury/budget, and transfer actual money. That would be a
public tariff. It would not establish private metrology or inspection benefits;
charging a fee alone is not evidence that measurement improved. Same-civ
`finance.transfer` returns zero, so a supposed self-payment cannot count as
inspection expenditure.

**Dependency blocked: insurance.** Public granary purchases currently receive
their grain immediately with deterministic transit decay. They do not own an
uncertain multi-turn shipment exposed to the merchant raid lifecycle. Merchant
receipts expose a real raid, but their cargo title and private payment accounts
are absent. Neither seam supports an honest insurance contract as it stands.
An eventual public transport-insurance experiment needs explicit buyer title,
a real delayed shipment/escrow, a funded insurer balance, premium/liability
limits, dated eligibility and actual loss settlement. A refund for deterministic
known decay would be a subsidy, not evidence for insurance against uncertain
voyage loss. Unknown imported voyages, partial capture and overflow must never
create financial entitlements.

## Proposed next registration, before implementation

Register **public procurement evidence**, without a behavior change:

1. Capture exact `BOUGHT` operations with the stable semantic purchase key,
   observed buyer/seller names, `sent`, `received`, `transit_loss`, actual
   `paid`, source/destination, turn and quantity/cash basis. Explicitly mark
   own-realm producer payments versus inter-civ treasury transfers.
2. Persist only the latest frame/fingerprint and scalar counters. Identical
   re-reads are inert; conflicting same-turn frames fail before committing.
   Store no run-lifetime purchase history in each policy or snapshot.
3. Compare output/RNG/native bytes with observation off/on. Test foreign
   treasury debit equals receiver credit, own-realm spending is an explicit
   sink, sent equals received plus loss, insufficiency/route suspension/budget
   exhaustion produces no invented purchase, source/destination key collisions
   are rejected, and exact checkpoint resume cannot recount payments.
4. Treat a raw state as historical public transaction data, never as proof
   that a saved merchant ID belongs to a reconstructed native pool. Preserve
   lineage when comparing independent same-seed runs; default seed namespaces
   are only trajectory-local.

This registration would establish a usable public accounting boundary. A later
behavioral proposal must independently state who pays whom, what physical or
informational service changes, what exposure exists before loss, and which
ablation distinguishes that service from a tax/subsidy. Current receipts do not
authorize charging fees or underwriting claims.
