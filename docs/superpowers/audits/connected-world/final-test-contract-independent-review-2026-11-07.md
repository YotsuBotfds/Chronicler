# Final registry-test corrections: independent review

Reviewer: B3 integration owner. **APPROVE** actual test-only commits
`403b9ea9181421b5be154412c9c28e6efac0fdfc` (integrated unchanged as
`79a7f411845348a8e28a6d1884f141b10f92192f`),
`0235b10b77a2c6ef0777494c56894885c60d1c44` and
`aeecbe2e737c99762935440996537fbf297cac94`.

Read every changed assertion and surrounding test, the actual livelihoods
switch/argument declarations and hook iteration, the historical and current
money-book registration, Rust transfer-purpose constants/validation, and the
FFI accessor. These commits change only seven existing test files; no runtime,
native, guard, witness or manifest changes are included.

The four enrollment updates preserve meaningful exact contracts:

- The completed acting suffix remains explicit and ordered; D3/A6/public-health
  readers precede X1's sole Phase 10 writer, followed by D2 and finally A1.
- The argument suffix includes the registered `wealth_accounting_mode`; this
  does not move the wealth observer from last place in hook order.
- The first five `MONEY_BOOKS` remain byte-for-byte the landed D1 prefix from
  `11467a46`, followed by the exact four new registered books. The test does not
  substitute a loose containment check for append-only ordering.
- Guild cooperation's completed suffix is checked exactly through X1, replacing
  the stale assertion that no new acting consumer could be inserted there.

The native updates retain exact purpose names and historical positions 0–9,
then append `restitution` at code 10. The native FFI returns that actual Rust
array. `transfer()` first rejects codes greater than or equal to its length;
therefore `len(sim.wealth_transfer_purposes())`, currently 11, is the correct
first invalid code. The new positive transfer case explicitly exercises code
10, and codes 8/9 remain tested as pairwise-only refusals. Existing exact
arrays, applied amounts/statuses and other invalid/duplicate cases remain.
This corrects stale registry assumptions without weakening the contracts.

Read D1's retained six-tail diagnostic receipts, including its original fourth
stale assertion failure, and the final 487-pass synthesis. This synthesis is
honestly labeled a diagnostic assembled from separate guarded invocations,
not a complete official lane. Read the lead's native correction logs: initial
two assertions pass, then all three affected native modules pass 17 tests in
15.46 seconds. These native runs are lead execution evidence; this review did
not rerun a native job.

Independently inspected the full official V4 offline receipt at
`/workspace/evidence/final-offline-v4/receipt.json`: source
`79a7f411845348a8e28a6d1884f141b10f92192f`, **75 chunks, 7,964 passed,
69 skipped, zero failures**, 336.1757 seconds total. Every guard passes, no
native module was loaded, and the slowest chunk is 34.3816 seconds against the
unchanged 110-second limit. Independently rehashed all **561** recorded input
paths against the current integrated checkout: no mismatch. Thus the receipt
still applies to its complete selected inputs despite later evidence and
native-test-only commits. Excluded native/subprocess suites remain excluded;
the full receipt does not claim to execute them.

No blocking finding. Final reviewed-head GitHub Tests and verified main CI
remain separate merge gates.
