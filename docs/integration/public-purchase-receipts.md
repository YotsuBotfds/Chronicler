# Public granary purchase receipts

This observation-only slice extends `--transaction-receipts` with a typed
`public_purchases` collection. It adds no switch, fee, insurance, private sale,
loan or economic behavior. Public granaries must actually run to produce this
domain. The [pre-registration](public-purchase-receipts-preregistration.md)
was committed before implementation on frozen integration `d051d7c0`.

## Committed public accounting boundary

At successful Phase10 granary return, the observer reads existing current-turn
`ReserveFlow(BOUGHT)` records appended by that pass (using its opening flow
window) and the exact opening projected treasuries,
demand and market-price vectors already computed for that procurement pass.
It never invokes another transfer, debits a stock, recomputes a target or
scans the accumulator per receipt. The kernel's existing authoritative flows
are not truncated or changed.

Each purchase records:

| Fields | Meaning |
| --- | --- |
| `id`, `source_turn` | Trajectory-local `public-grain` purchase identity and committed simulation turn |
| `source_region`, `dest_region`, names | Actual market and recipient granary, with names frozen at capture |
| `buyer`, `keeper`, `source_controller`, names | Recorded public purchaser, recipient granary keeper and selected selling ruler; no private merchant title |
| `purchase_kind` | `own_market`, `same_realm` or `foreign` |
| `sent`, `received`, `transit_loss` | Exact existing source debit/recipient credit and their difference |
| `buyer_paid` | Actual whole treasury payment in the committed flow |
| `foreign_ruler_credited` | Matching inter-civ treasury credit, or zero for domestic purchases |
| `domestic_producer_sink` | Existing own-realm producer payment, or zero for foreign purchases; not an agent cash account |
| Buyer/seller treasury before/after | Replay of these exact purchase legs from the already computed opening keep projection; domestic seller balances are absent |
| Buyer/source demand, `source_market_price` | Actual procurement input vectors, with an explicit price basis |

The price is the supplied economy result's food demand over market supply,
with the existing 0.1 floor. This is the price actually used by procurement,
not a new monetary price or a retrospective private sale valuation. Accumulator
projection honors already-applied watermarks and pending keep changes. The
observer replays only successful purchase legs; inter-civ `finance.transfer`
already verifies the actual paid amount equals the flow cost.

The ID is `{namespace}:public-grain:{turn}:{buyer}:{destination}:{source}`.
It names a one-turn committed public purchase, never a native merchant voyage.
The default seed namespace is trajectory-local; joining independent runs also
requires run/source lineage. All rows retain `financial_eligible=false` for
automatic downstream fees or claims.

## Separate clocks, bounds and historical integrity

Native mobility and public procurement retain distinct source turns, phase
labels, fingerprints and completeness. Public phase is
`phase10_granary_procurement`; it does not borrow the native mobility clock.
The existing cap applies separately to each domain (default4096, maximum65536).
Only the latest public frame/fingerprint and scalar cumulative counters persist.
No lifetime transaction-row list grows in a policy or snapshot.

`available=true, complete=true, rows=[]` is an observed successful pass with no
purchases. A dated unavailable frame means the pass lacked its economy/basis.
An absent or stale public frame exports `source_turn=null` and
`unavailable_reason=not_captured`; it never pretends to have observed zero
activity. Disabling or dormancy keeps the existing receipt gating rules.

Overflow reports dropped rows and `complete=false`, while authoritative
purchases continue unchanged. Duplicate retained semantic keys are omitted and
counted as dropped/incomplete. The key set is bounded by the cap;
`retained_key_duplicates` counts only collisions with those retained keys.
`duplicate_detection_complete=false` explicitly marks unknown duplicate counts
after any cap overflow. Overflow already makes the unchecked remainder
incomplete. Scalar public counters sum all observed authoritative
flows, even when row storage overflows; they are not financial entitlements.
An identical repeated capture is inert. Conflicting same-turn and reversed
captures raise before changing the public journal.

Snapshots export detached current public rows and their frozen names. They do
not reinterpret earlier names or keepers from current/final ownership. A
schema-old enabled receipt model can be restored by Pydantic pickle without
new Field defaults running; explicit `__setstate__` backfills missing
`public_purchases` to unknown None. JSON loading does the same by validation.
Old purchases are not reconstructed. Exact checkpoints preserve both domains;
the existing fresh-native-pool guard remains in force for saved native IDs.

## Validation scope

Tests were written during the reserved quiet benchmark and executed only after
its owner announced completion. The public, existing merchant receipt and
existing granary selection passed **92 tests in 8.65s** against the isolated
receipt release. This includes actual own-market/same-realm/foreign purchase
legs with direct and projected accumulator payments, schema-old Pydantic pickle
restoration, real two-purchase overflow and duplicate/conflict behavior.

Full-turn native controls compare economic WorldState, events, RNG, native
payload bytes and agent snapshots every turn with observation off/on; the
controlled run must make actual public purchases. Exact RunState checkpoint
continuation preserves both domains through subsequent real turns. Public
snapshots and native mobility clocks are tested independently.

The bounded offline selection passed **74 tests, 2 native skipped in 1.08s**,
guard PASS, no native modules loaded and no blocked I/O. The existing receipt
release is unchanged: native crate tree
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`, extension SHA-256
`fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`.
There was no Rust edit or new build. Evidence is retained outside Git under
`/workspace/chronicler-public-purchase-evidence`. These are bounded component
checks; complete integration/scientific gates remain separately recorded.

Independent read-only review confirmed treasury replay, sink/credit separation,
phase windows, frozen names and schema-old pickle handling. Its cap1/A,B,B edge
led to explicit `retained_key_duplicates` naming and a
`duplicate_detection_complete` flag: the bounded recorder cannot claim to count
duplicates among discarded keys. Unavailable capture also has unknown scan
scope. An early candidate frame's pickle preserves known retained counts while
backfilling unknown duplicate scope, without recreating old transactions. The
expanded public selection passed 23 tests; its pure selection passed 21 tests
under the offline guard. No further blocker was found by the reviewer.
