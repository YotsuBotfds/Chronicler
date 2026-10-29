# Scrubbed debt-holder detail — 2026-10-29

Source: `d0281e5f57c508f27cea1676f36e0e6ed1225c9d`, which already carries
PR #68 and the data-layer mixed-history missingness corrections.

A resumed older run can contain early finance snapshots without named holder
records and later snapshots with them. The Finance panel selected its current
detail from the richest record anywhere in history. At an older snapshot with
positive foreign debt it therefore said “no foreign lender” and displayed
lender-only table columns and explanatory text.

The current tiles, table columns and note now use the scrubbed snapshot's
recorded detail. Charts still include the later lender observations, and the
existing null gaps, unknown write-offs and cumulative-difference rules remain.
No simulation, serialization, fixture, default or runtime identity changes.

Two integration regressions exercise an older kinds-only snapshot and an older
finance-only snapshot in otherwise newer history. Both check positive foreign
debt remains “one total”, lender-only columns and write-off tiles stay absent,
and scrubbing forward restores recorded lender detail. Existing real-shaped
fixtures are copied for the legacy projections; original files are unchanged.

Verification is pending. The managed execution environment is unavailable:
no test, lint, build or browser result is claimed for this patch. Root will run
viewer checks before integration.

Independent read-only snapshot review found persistent keys and principal/rate
aggregation sound. A separate gap remains: post-collapse write-off events exist
when the fallen borrower's finance row is absent, so the dedicated loss view
needs event-backed missingness handling. That is separate work.
