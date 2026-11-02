# Crisis development performance observation (2026-11-02)

One procedural seed-42, 32-region, 10-civilization, 40-turn hybrid simulation was run with CLI defaults, simulation only, `PYTHONHASHSEED=0` and OMP/OpenBLAS/MKL/NumExpr/Rayon threads set to one. Each measurement is a fresh process and includes startup, world generation, simulation and output writes. Optional crisis controls were not enabled. This is a narrow development observation, not a feature-enabled performance or scientific qualification.

The original baseline was source `6ff45ec33a86ff72b84d0d493fefcc3cd3a89601` with its matching native build. The current source was `cb816603f6c30138922e59b9ba89ffaf7d150b5b`, Rust tree `543df3bb74804c71cf16046a7cac8f43ea9bfe45`, with native extension SHA-256 `d15cb4c3f7e71778ce9127688486aba85a01459c344dcbb3dfd8e3331e824b8d`. Both ran with CPython 3.13.5 and their respective matching compiled extensions.

Three initial current runs during other work took 6.0520, 4.0093 and 5.1931 seconds (median 5.1931), compared with a previously recorded baseline median of 2.8020 seconds. A single matched cProfile run did not reproduce that gap: baseline and current profiles totaled 6.304 and 5.906 seconds, respectively. Profiling changes timings; these samples do not identify a cause for the initial gap.

After other heavy work stopped, three alternating baseline/current pairs took:

| Run | Baseline wall seconds | Current wall seconds | Baseline peak RSS KiB | Current peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2.8292 | 2.6755 | 163,332 | 170,684 |
| 2 | 2.7292 | 2.7052 | 163,400 | 169,280 |
| 3 | 2.6084 | 2.6823 | 163,976 | 170,608 |
| Median | 2.7292 | 2.6823 | 163,400 | 170,608 |

The quiet wall-time difference is too small a sample to establish a speedup or rule out a regression. Median peak RSS rose by 7,208 KiB (4.4%) in this case. Linux `ru_maxrss` reports process peak resident size in KiB, not retained heap size.

Every quiet run completed turn 40 with 32 regions, 10 civilizations, 40 native household-stat entries and 5,934 native agent-event rows. Each generated 16 files. Baseline/current bundle sizes were 2,224,098/2,472,132 bytes; compact encoded history sizes were 879,200/1,127,234 bytes; total generated regular-file sizes were 4,853,141/5,101,175 bytes. The 248,034-byte increase in each is the intentionally added `food_accounting` history: removing that field from current decoded snapshots makes the 40 snapshots and encoded history match the baseline. The bundle size covers the entire bundle, not just history.

Raw timings, per-run output witnesses, both profiles and their cumulative/self-time top-30 tables are retained under `/workspace/shared/chronicler-crisis/m9-current`. These are one-seed results on a shared machine, not a general performance guarantee. The browser/viewer path is not measured here.
