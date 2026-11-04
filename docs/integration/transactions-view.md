# Historical transaction observations

The Food tab includes a Transactions section when its saved history records
`transaction_receipts`. It reads no final-world journal. A run with no recorded
receipts has no section; an earlier or missing snapshot remains unknown.

Native merchant mobility and Phase 10 public granary purchases are independent
domains. Each must identify snapshot turn minus one, and every actual row must
have that same source. A malformed/future native domain does not hide valid
public purchases, or vice versa. A public-only snapshot can have a null native
source. A not-captured public marker needs its own dated `as_of_turn` and remains
unavailable, distinct from a complete available frame with zero purchases.

The native table preserves each operation's exact quantity basis. Reservation,
departure, crossing, arrival and active-commitment observations are not summed
as trade turnover or independent voyages. Shared regional stock and virtual
shadow cargo have explicit labels and a filter. The good-slot labels use the
fixed economy/FFI order, not the different ResourceType order. Voyage IDs are
known only when the observation records one; missing continuity is unknown.
Regional controllers and merchant affiliation are frozen observations, not
claims of private cargo title, merchant cash, sale settlement or insurance.

The public table separates grain sent/received/lost, actual buyer treasury
payment, actual foreign ruler treasury credit and the domestic producer sink.
The sink is not credited to a private account. Buyer/seller before/after values
replay only the projected keep purchase legs, not whole-turn final balances.
Demand, source market price and exact quantity/price/treasury bases remain
inspectable. Domain observation IDs are plain provenance text; no Event links
are invented.

Completeness, execution/availability and dropped rows remain explicit. A capped
native frame does not establish complete voyage continuity; an unexecuted phase
is not an observed zero-trade result. Public retained-key duplicate counts are
never presented as total duplicates when detection is incomplete. Missing older
duplicate-scan fields are unknown. Partial retained rows remain visible without
an inferred complete purchase/cargo total. The saved-frame history stops at the
selected snapshot, keeps missing domains unknown, and seeks the exact saved
turn. Lists initially show 40 rows and can expand; source arrays are untouched.
Saved-frame validity is computed per history array before selecting the visible
prefix, avoiding a scan of every historical cargo row on each scrub.

## Controlled fixture scope

`transaction_observations.json` contains only actual captured summaries from six
separate producer exports, each with its source label and original bundle SHA:

- `public-own-market`, `public-same-realm`, `public-foreign`: actual controlled
  Phase 10 procurement passes at source 30/snapshot 31, with no native mobility
  capture. These are not complete simulation turns.
- `native-bridge` and `native-shadow`: four actual controlled bridge ticks with
  held market inputs; public procurement is not captured. Shadow observations
  represent virtual cargo.
- `hybrid-public`: five actual complete hybrid turns with primed grain stocks
  and harvest variance, recording both domains.

All were exported by producer source `18d9b7c3`, extension SHA
`fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`.
No worlds were combined and no ordinary world-history fields were filled from
final state. They are controlled mechanical evidence, not a scientific gate.
Tests add explicitly modified dates/caps only to exercise reader rejection and
partial-history behavior; those variants are not natural-run claims.

Regenerate the safe summary fixture from the producer's exported subdirectories:

```sh
python viewer/scripts/build-transaction-observations.py PATH_TO_FIXTURE_FOLDER
```

The builder decodes ordinary bundles and copies recorded summaries; it requires
the producer's fixture-source label and does not manufacture absent snapshots.

## Reader verification

The initial reader/transport/systems integration selection passed 73 tests with
one worker. After memoizing saved-frame validation, the 22 relevant reader and
transport tests, ESLint and production build passed again. The broad viewer
suite is deferred until the core qualification slots are available.

Desktop (1440px) and mobile (390px) browser checks used all six complete exported
bundles above. They compared native quantities/bases and public grain/payment
legs with the source rows while seeking forward and backward; exercised native
versus shadow filters and the operation-filter fallback after an earlier scrub;
and checked pre-first-snapshot, removed-history, legacy and independently
future-dated domain cases. No console/page errors or document/section overflow
occurred; wide tables scroll internally. The external viewer evidence directory
retains the smoke script, source-derived diagnostics, report and screenshots.
