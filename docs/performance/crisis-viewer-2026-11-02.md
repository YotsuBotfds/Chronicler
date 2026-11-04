# Crisis viewer: bounded saved-world browser timings

Three paired Chromium trials on the same current saved world show similar overall load and interaction times for the baseline and current viewer, with variability across trials. These measurements do not establish a general speedup or regression. No viewer optimization was made as a result.

## Input and method

The input is the preserved current 32-region, 10-civilization, 40-turn, seed-42 hybrid simulate-only run, `quiet/current/run-1/chronicle_bundle.json`, 2,472,132 bytes, SHA-256 `a6ef48c13512b3efa4585cab51d1d0f7240139d4bbc3f273b2c4a0ef0f0d8dca`. Its producing source was `cb816603f6c30138922e59b9ba89ffaf7d150b5b`; native tree and binary identities and generation command are in `/workspace/shared/chronicler-crisis/m9-current/receipt.json`. The measured viewer builds were baseline `6ff45ec33a86ff72b84d0d493fefcc3cd3a89601` and current `7c0ca9147af5b0c73131f4c0480676c88c54dc7b`, production-built with existing dependencies and Node 20.19.0. The baseline preview used port 4179 and current preview 4178; the existing measurement harness also serves the two build directories on its own local ports. The current build contains M8 transport-control and regional-food fallback changes, but this workload does not measure a live what-if run.

Headless system Chromium 154.0.8037.57 used a 1920 × 1200 viewport, fresh browser context per sample, five visible logical CPUs, a four-CPU cgroup quota, 16 GiB memory limit and no CPU throttling. Samples ran serially in alternating order: baseline/current, current/baseline, baseline/current. This was a shared host, not a controlled dedicated machine. The same current bundle was used in both viewers; the result isolates neither the change in data size nor any one code change, and does not compare the baseline-generated world with a current-generated world.

The external copy of the existing `perf-viewer-inspection.mjs` harness from the prior viewer history/frame work used its same browser event, DOM mutation, forced-layout and next-frame approach. The 40-turn workload seeks turns 11–30 instead of 81–100; twelve history metric changes alternate soil/water, and twelve comparison endpoint changes alternate turns 20/40. It opens the region history inspector and loads the same saved file into the left side of completed-run comparison. Optional CPU profiling was disabled; this sample did not establish a specific code bottleneck warranting a change. An interrupted preliminary sample overlapped other work and is retained but excluded. All six completed trials recorded zero browser console warnings/errors, zero seek failures and zero history/metric/comparison interaction timeouts.

## Measurements

Milliseconds; entries are the median of three per-run medians, with the range of those run medians. Overview and history scrubs have 20 steps each; metric and comparison endpoint actions have 12. The harness calls its event-to-DOM-mutation elapsed time “script”; it can include scheduling and waiting and is not isolated CPU time. “Commit” additionally forces a layout; “frame” is elapsed to the following animation-frame callback and posted task, not a guarantee that pixels were presented. File-load frame measures elapsed from the input change to the observed overview or comparison result and the following frame.

| Interaction / measure | Baseline | Current |
| --- | ---: | ---: |
| Saved-world overview load, frame | 377.5 (309.8–406.8) | 383.6 (323.3–400.6) |
| Overview timeline seek, script | 9.15 (8.80–9.25) | 8.25 (7.95–8.70) |
| Overview timeline seek, frame | 44.65 (41.45–44.75) | 46.50 (42.15–48.35) |
| History inspector open, script | 69.6 (55.4–82.3) | 72.5 (67.3–82.0) |
| History inspector open, frame | 308.3 (143.1–319.6) | 283.6 (274.5–294.4) |
| History-open timeline seek, script | 17.10 (13.10–19.10) | 14.40 (12.60–16.20) |
| History-open timeline seek, frame | 59.95 (54.35–61.55) | 51.70 (49.20–57.95) |
| History metric selection, script | 24.80 (18.30–27.45) | 18.05 (16.55–18.35) |
| History metric selection, frame | 30.70 (28.55–31.45) | 29.70 (26.20–29.85) |
| Completed comparison file load, frame | 124.6 (123.2–124.7) | 130.0 (106.3–144.1) |
| Completed comparison endpoint, script | 3.85 (3.70–4.00) | 3.60 (3.45–3.60) |
| Completed comparison endpoint, frame | 26.45 (25.75–27.30) | 24.60 (23.95–33.80) |

History-open frame samples have especially wide ranges. Faster medians in some paths and slower medians in others are descriptive for this one world and small trial count; they do not demonstrate an improvement or identify its cause. This check does not measure mobile, long histories, live streaming, or native simulation performance.

The raw samples, per-run and aggregate summaries, harness copy, hashes, build logs and excluded interrupted log are in `/workspace/shared/chronicler-crisis/m9-viewer/`. The distinct native simulation timing evidence remains in `/workspace/shared/chronicler-crisis/m9-current/`.
