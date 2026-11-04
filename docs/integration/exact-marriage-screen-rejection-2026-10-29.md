# Exact-near broad phase: complete first-screen rejection — 2026-10-29

The first fixed screen at `1421621b` / [run 40884490492](https://github.com/YotsuBotfds/Chronicler/actions/runs/40884490492), attempt 1, is **COMPLETE REJECTED**. Root and independent non-author byte/source/arithmetic reviews qualify this complete rejection. Provider FAILURE records the intended rejection: the screen exits 101, the owner exits 1, and always-closure/upload both succeed. It is not an incomplete build or cleanup failure.

All six ordinary differential contracts and the original radius contract pass. The separately selected ignored screen preserves **15 parity rows, 150 timing samples, 15 decisions and one final record**: 12 criteria pass and three fail. Each case has five fixed alternating old/candidate pairs; medians use the complete `total_ns_with_drop` column.

| Synthetic case | Old median µs | Candidate median µs | Frozen maximum µs | Change | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| empty0 | 0.124 | 0.147 | 5.130 | +18.55% | PASS |
| singleton1 | 0.410 | 0.515 | 5.430 | +25.61% | PASS |
| small16 | 0.709 | 0.813 | 5.744 | +14.67% | PASS |
| spread255 | 64.261 | 66.652 | 72.474 | +3.72% | PASS |
| spread256 | 64.279 | 65.993 | 72.492 | +2.67% | PASS |
| spread257 | 64.749 | 113.100 | 67.986 | +74.67% | FAIL |
| spread1024 | 982.298 | 983.063 | 884.068 | +0.08% | FAIL |
| spread4096 | 15935.399 | 15916.035 | 14341.859 | -0.12% | FAIL |
| dense1024 | 987.484 | 999.910 | 1036.858 | +1.26% | PASS |
| dense4096 | 16130.452 | 16451.970 | 16936.974 | +1.99% | PASS |
| boundaries1024 | 973.781 | 537.835 | 1022.470 | -44.77% | PASS |
| outside1024 | 975.364 | 999.858 | 1024.132 | +2.51% | PASS |
| nan1024 | 5.542 | 5.532 | 10.819 | -0.18% | PASS |
| infinity1024 | 5.962 | 6.007 | 11.260 | +0.75% | PASS |
| zeros1024 | 985.070 | 1000.956 | 1034.323 | +1.61% | PASS |

Large spread 1024/4096 cases require at least 10% improvement; spread257 allows at most 5% regression. Other frozen caps and exact integer rounding remain in the JSON. Spread4096 removes **47.21% of distance evaluations**, yet improves wall median only 0.12%; spread1024 is slightly slower. The 44.77% boundary-case gain remains visible but cannot override the all-case rejection. No cutoff tuning, retry, selective rows or production wiring follows.

The only crate change is the frozen `cfg(test)` appendix; the complete original 090 production prefix is unchanged. The fresh release binary record is SHA256 `b17c2240797c608c7cc56cd525e178762158fd98b02c1c784e599cbf47a387b4`. Actual remote compiler/runtime/source/binary/linkage before/after/terminal records reconcile, with one affinity CPU and thread caps 1. The binary was not downloaded, rehashed or executed by this consumer.

All **49 original ZIP members  / 250,783 expanded bytes** reconcile: 48 owner files plus the always-closure file. All 32 child logs are full, with 32 complete cleanups and 32 exits, exactly one 101. The **650,249-byte raw progress stream is HASH-ATTESTED ONLY**: not uploaded and not independently rehashed. This distinction is preserved in the JSON and peer receipts.

GNU Time reports build 334.40s wall/321.15s user+system CPU/1,380,288 KiB peak RSS and screen 0.79s/0.76s/7,528 KiB. These are per-command observations, not total workflow CPU, whole-planner or production simulation costs. The independent reader's initial comment-before-`cfg(test)` assumption failure is preserved; only that observer predicate changed.

This is a curated projection, not the producing readout. [JSON companion](exact-marriage-screen-rejection-2026-10-29.json) pins every case/sample, source/runtime/artifact identity and expiry. No World, geometry replay, native import, build/test rerun, main merge, scientific result or broader performance claim is supplied. Final independent peer SHA256: `f9779ee0f386efe5d9750664173c647bcd87f1109600efc75a93186c851cf7ac`.
