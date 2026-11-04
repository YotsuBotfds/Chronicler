# Science receipt chronology review follow-up

The semantic review of the [initial independent readout](scientific-receipts-audit-development-2026-10-28.md)
found that the observer accepted some terminal trial dates the runtime cannot
produce. The source correction `c297b40e5ee323e359ac1a5711b003e1cd940df6`
requires funding < planned completion ≤ actual resolution for completed and
cancelled trials. Failure may occur at funding before planned completion;
otherwise failure must also wait until planned completion. A cancelled record
cannot use the funding-time exception.

The valid funding-time failure fixture now uses the runtime's turn-1 funding,
turn-2 completion plan and actual turn-1 failure, with empty/default measurement
fields. Additional regressions reject same-turn completed/cancelled work,
completion plans at/before funding, premature cancellation and a failed record
that resolves after funding but before planned publication. A separate valid
v2 publication failure after planned completion remains accepted.

Focused Python 3.13.5 offline verification passed **137 tests**: 49 science
receipt tests plus the existing 56 audit and 32 comparison tests. The guard
recorded no native imports, network attempts, subprocess attempts or oracle
runtime calls. This remains an observer check, not a new simulation gate.

All ten original natural-study bundles were rescanned read-only in a fresh
external directory at corrected observer `c297b40e`. Each complete 0–59 audit
remained at **0 errors / 0 warnings**, all **6 strict 1–59 contrasts** remained
matched, and both normal continuations retained their limited exported-Python-
world identity. All **22 JSON/Markdown audit and comparison files** were byte
identical to the prior observer's outputs. The raw study and earlier observer
readouts remain unchanged. Exposure limits and lack of v2 study data remain
exactly as stated in the initial readout.

| Retained artifact | SHA-256 |
| --- | --- |
| Original study manifest | `b65f193077e290f324a0ee92e191b46530032eaaebf6b525efcfbdce87d49ab5` |
| Chronology-corrected readout JSON | `fcda2af1e015f1e2fc353a6e65071f2607d4750bde395183ac08f984a62e1a6d` |
| Unchanged strict comparison JSON | `3083ca1712dd4da569430a71d02d4ce0cecb7a92434cd2ef7e6dca0f23223143` |

The review also identified optional future checks for cumulative withheld-result
counts and first-inspected-turn withholding. Those are not part of the verified
contract here; no efficacy or full archive-receipt reconstruction is claimed.
