# Fallen-borrower loss visibility — 2026-10-29

Draft atop the scrubbed-detail fix at `00585a47b5fa4c695c588cb62411b87f815ab363`.
No simulation or serializer changes.

In Phase 3b, `finance._write_off_dead` records an extinct borrower's write-off
and emits `debt_written_off`. Both finance and holder snapshots deliberately
contain living borrowers only. The dedicated loss list and turn strip previously
required a cumulative rise in a finance row, so they dropped that event even
though the general credit-event list retained it.

The dedicated view now retains borrower-first default/write-off events where
the first covering finance snapshot lacks that borrower's row. Events have no
typed principal amount, so these entries show an unknown amount. No prose is
parsed and no synthetic zero-debt row is created. A missing current holder record
also says it is missing instead of claiming the borrower owes nothing.

Event-only entries group loans by their first covering snapshot; an event at
tick T belongs to a snapshot after T. An event beyond the last completed
snapshot remains pending. Events already linked to a cumulative result are
excluded from the fallback, including a temporarily absent row followed by a
later cumulative observation. Lender-only actor matches are excluded.

The strip receives the same event evidence as the dedicated list. It labels
event-only write-offs “amount not recorded”, including finance-only bundles;
a default event without a distinct write-off event adds a default mark only.

Three pure regressions cover grouped loan losses, sparse snapshots, borrower
identity, pending final events, event-only defaults, and later cumulative
deduplication. A component regression projects a fallen borrower from the real
fixture and checks unknown amount, event selection, strip visibility and missing
record wording. The projected loss event is explicitly synthetic test data.

Independent source review cleared the implementation; execution is pending.
Runtime is unavailable locally; no test,
lint, build or browser result is claimed.
