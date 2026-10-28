# Independent default-export artifact verification — 2026-10-28

[Reader run 40788984730](https://github.com/YotsuBotfds/Chronicler/actions/runs/40788984730)
passed at exact reader source `53631aafd1490057356b475d072c9b20d8ddb0e9`.
All 18 reader contract tests passed (0.061 seconds). The reader then downloaded
and checked the already completed artifact; it created no simulation worlds or
native pools and left all original evidence unchanged.

The original 54,788,314-byte ZIP matched SHA-256
`025f4c215b1a2e3a556af45dc9d099c9f14343d0ba50ba9c896d8e92be37e8ff`.
Its pinned index and all **974 payload files** matched, including raw outputs,
source snapshots, audits, 36 probes, 18 driver provenance receipts, the wheel
and the compiled binary copy. Input hashes were checked again after reading.

The frozen candidate comparator, with its existing timestamp/log/manifest rule,
independently returned:

| Case | File pairs | Differences |
| --- | ---: | ---: |
| hybrid_s1234 | 10 | 0 |
| hybrid_s42 | 111 | 0 |
| hybrid_s7 | 111 | 0 |
| off_s42 | 9 | 0 |
| off_s7 | 9 | 0 |
| proc48_hybrid_s42 | 92 | 0 |
| proc48_off_s7 | 15 | 0 |
| scaled22k_s42 | 32 | 0 |
| scaled52k_s7 | 10 | 0 |
| Total | 399 | 0 |

Sources remain baseline `2f9d618b70f3304c02dcaeef12996b4a99e074c0` and candidate `d0281e5f57c508f27cea1676f36e0e6ed1225c9d`,
under original control `db7ec48b`. The original 18 runs/3,200 turns are the
same evidence, not additional replications. Reinspection took 23.20442095 seconds;
it establishes no simulation speedup, feature efficacy, or checkpoint/RNG identity.

Reader artifact `12861140665` retains the compact result, comparator log and test
output. Its GitHub-reported ZIP SHA-256 is
`0537dc24d2ba3891b42366b0c27f2f9b99fc4820ad1954d9cab9288d224d74a7`.
The [machine-readable verification](default-output-artifact-verification-2026-10-28.json)
records exact IDs, counts and pins.
