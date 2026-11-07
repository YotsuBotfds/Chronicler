# Corrected contracts, optional archives and bounded viewer checks

This packet follows the separate [pure formatter performance result](../connected-world-rework-viewer/README.md). It contains viewer compatibility, transport and functional evidence, not a new simulation screen or qualification result. No narration calls, simulation runs, native builds or default promotion occurred in this lane.

## Source and contracts

- `78fac6f2028d932ab09a7fcac1f43b4b9b2b584a`: old and corrected X1, public-health and A6 readers and displays.
- `160a8027`: legacy rules1/2 rows are **prepared proposals**; corrected rules3 rows are actual installed inputs. Neither establishes a move or causal outcome attribution.
- `5e41223b2513b17cfb3350c437cc1a96111001a3`: optional gzip uploads, retaining the same strict decoder and the identity of the original uploaded artifact.
- `71accf9449965ac77936e69f0391ef9a43b5bbcd`: phone prose/table containment and the independently reviewed cost-only label correction.

The established defaults remain A6 rules2 and public-health `legacy_displacement`. Rules3 and `density_only` are explicit corrected opt-ins. The viewer accepts legacy bundles and does not rewrite their observations.

New X1 residence-arrival counts are separate from motive-classified displacement spells. Each living observed person is counted once at their current recorded residence; returns and trips ending elsewhere may count. Arrival does not establish forced displacement or measured housing pressure. Incomplete coverage/window means a population arrival share is unknown, not zero; partial counts are not ratios or lower bounds. A new frame with positive recent arrivals is not classified as a recorded zero. The reader checks the optional group as a whole and regional/total count closure, without inventing the producer's observation watermark.

Corrected density mode adds no motive-derived susceptibility multiplier; the existing regional density authority remains. Its configured neutral multiplier is dated at the explicit current `crowding_source_turn`; prior residence/water and recent-arrival observations retain their T−1 source. Old missing fields retain legacy meanings. Actual application, components, would-be personal inputs and native movement receipts are shown separately. Independent D3 inputs survive personal controls. Bounded omitted rows remain unknown. In cost-only mode the display now says care/sanitation benefits are disabled while quarantine controls are retained; it no longer claims every protective effect is disabled.

## Optional lossless gzip upload

The original natural 120-turn FULL-p19 bundle is unchanged: SHA-256 `f6cb5562a4aaec888b6f2a03b4c4b01bd1e8d49737aec22673034eba30ce0ee2`, 37,962,968 bytes. The storage lane's optional level-1 archive is 9,460,726 bytes (75.08% smaller), SHA-256 `0caf4aa01962c83052e41895bd8b5945f54630a334770eacb85896f4b3fdc790`. The archive helper verified a byte-exact round trip and retained the source. See [archive receipt](archive-receipt.json).

The file picker accepts `.json.gz`/`.gz`; gzip is recognized by `1f8b` magic, not the filename. Browser `DecompressionStream` inflates it before the existing BOM, checkpoint-header, JSON and v6 history validation. Worker and fallback use this same path. A compressed input is fully checked before any decoded parts are published; a CRC-corrupt archive that contains otherwise valid JSON must not open. Unsupported browsers receive an extraction message. The original compressed bytes determine file name, size and SHA-256, so a JSON file and its archive intentionally have different bookmark/artifact identities. No default export format or compression dependency was introduced.

[Complete production-code comparison](archive-equivalence.json) proves identical expanded bytes, decoded values/key order, all 190,555 indexed observations, 3,279 identities and 28 dated history queries. It retains all 6,663 events and 357 named events. The full index digest is `e7ffba50d7dc1f5af237530b3c0598a05e377f54d0b58d20789ea6471f499e2c`; query digest is `921241e957eee1cb67f69e2d1534e377306db9b770fc6725aa63509052390124`. These compare plain/archive under the same compatibility source. They differ intentionally from the earlier pure-formatter digest because later compatibility commits change explanatory wording, including prepared versus installed inputs; do not compare them as an optimization identity claim.

The actual saved-bundle upload/linked-history journey passed 32 desktop/phone checks, including original artifact identity, actual named wages, stable person/project links, source pointers, search and timeline navigation. The [browser receipt](archive-browser.json) includes decode phases, with inflation inside the timed decode interval.

## Same-build loading costs

The four-sample timing pilot took 27.47 seconds. Before the accepted run, the declared ceiling was 300 seconds for 24 samples: three repeats × plain/archive × desktop/phone × worker/forced fallback. The pilot projection was 164.83 seconds, 247.25 seconds with 1.5 margin. Actual accepted elapsed time was 141.51 seconds. Every sample is retained in [raw results](archive-profile.json); [summary](archive-summary.json) retains ranges, individual paired differences and budgets. OS caches may be warm. Phone means a 390×844 Chromium touch viewport on this host, not a physical handset.

Median complete load milliseconds, same production build and expanded data:

| Decode path | Viewport | JSON | Gzip | Change |
|---|---|---:|---:|---:|
| Worker | Desktop | 1,897 | 1,996 | +5.2% |
| Worker | Phone | 1,780 | 1,876 | +5.4% |
| Forced fallback | Desktop | 1,512 | 1,632 | +7.9% |
| Forced fallback | Phone | 1,426 | 1,486 | +4.2% |

All four predeclared median load budgets (archive ≤ 1.5×JSON + 500ms) and cold/warm panel budgets (archive ≤ 1.2×JSON + 200ms) passed. Loading is slower with the archive. Warm reopening also worsened in worker phone and both fallback medians; raw mixed outcomes are retained. Since the history products and frontend are identical, panel timing differences do not establish a gzip speed benefit. Fallback wall times do not justify removing workers: main-thread responsiveness is a different cost. This transport change does not reduce expanded history size, simulation CPU, or demonstrated RSS. No memory reduction is claimed.

## Residual index cost

An isolated sampled CPU diagnostic used the immutable pure-formatter runtime from the earlier packet and the same unchanged FULL-p19 input. Its index digest remains the original `ff4554e9…`; indexing took 770ms under the sampler. Garbage collection and construction/joining of authoritative rows are now the largest sampled application frames; reused number formatting occupies about 38ms. Inspector startup/post overhead is visible separately (190ms), not treated as simulation/viewer work. [Raw diagnostic](residual-index.json) and [CPU samples](residual-index.cpuprofile) retain every frame. This is one diagnostic, not an acceptance benchmark. An unmeasured permanent global-index cache was not added: it would retain rows across tab unmount and needs a memory tradeoff measurement.

## Real corrected records and phone regression

The actual development smoke bundle is template seed5, 8 turns, producer `09403c15070ddab4977ae8b2e65c336238468447`, native SHA `b1d3ea5ac858681960b2cb880c534164905501f6ab4f6f3c94f7c9b5f66196cd`. Its [producer command](corrected-producer-command.json) explicitly selects rules3/all/density_only. Seed5 is a reused development seed; this is not held evidence. All eight snapshots pass the production strict readers, all 3,776 linked observations have resolving pointers and valid clocks, and early incomplete arrival shares remain unknown. [Reader receipt](corrected-records.json), [producer harness](corrected-producer-harness.json).

Actual desktop/phone journeys passed 46 initial A6/X1 checks and 78 public-health checks. They compare exact retained applied/component/would rows with independent Python decoding, rather than asserting favorable model outcomes. This 8-turn smoke has no repair wage receipts; no such witness was fabricated. Its arrival windows remain incomplete, so that smoke alone does not establish a complete-window browser witness. The later [120-turn follow-up](complete-window-120.md) supplies the actual complete-window transition and checks.

Visual inspection found a real defect missed by the original document-overflow check: on the phone at snapshot8, residence prose extended to x573.9 inside a section ending at x365. The enhanced paragraph/table bounds regression fails on the old CSS ([before](layout-before.json), [screenshot](phone-before.png)). A single explicit `minmax(0,1fr)` grid column keeps prose within the section while wide tables scroll internally. All 50 strengthened desktop/phone checks then pass ([after](layout-after.json), [screenshot](phone-after.png)). Existing aggregate and individual histories remain intact. The initial weaker checks are retained as such, not presented as proof they caught the defect.

Legacy compatibility also passed the previously saved 200-turn health world's 90 desktop/phone checks and the original natural bundle's 1,200 package-reader checks. These do not establish scientific qualification or an alternate simulated story. [Legacy browser](legacy-health-browser.json), [legacy reader](legacy-records.json).

## Checks and reproduction

At `5e41223b`, the full viewer suite passed **194 files, 1,786 tests, 2 conditional skips** in 297.59 seconds; lint and production build passed. After the small label/layout follow-up, all four focused public-health tests, lint, build and the strengthened actual browser regression passed. The full suite was not repeated for the seven-line follow-up; integrated CI remains the lead's merge gate. Build warnings about large chunks remain. See [check receipt](checks.json) and compact logs. No Rust/native/simulation or restricted 200-seed/procedural gate was run here.

Examples (set paths to retained inputs and installed local tools):

```sh
npm --prefix viewer test -- --maxWorkers=1
npm --prefix viewer run lint
npm --prefix viewer run build
node docs/superpowers/progress/connected-world-rework-viewer-compatibility/verify-archive.mjs --root "$PWD" --plain /path/chronicle_bundle.json --archive /path/chronicle_bundle.json.gz --out /tmp/archive-equivalence.json
NODE_PATH=/path/to/playwright/node_modules CHROMIUM_EXECUTABLE=/usr/bin/chromium PYTHONPATH=src node docs/superpowers/progress/connected-world-rework-viewer-compatibility/profile-archive.mjs --config docs/superpowers/progress/connected-world-rework-viewer-compatibility/archive-profile-config.json --out /tmp/archive-profile --python /path/to/python
NODE_PATH=/path/to/playwright/node_modules CHROMIUM_EXECUTABLE=/usr/bin/chromium PYTHONPATH=src node viewer/scripts/qa-connected-world.mjs --build viewer/dist --bundle /path/chronicle_bundle.json.gz --out /tmp/archive-browser --python /path/to/python --journey history --turns 27
node docs/superpowers/progress/connected-world-rework-viewer-compatibility/validate-corrected.mjs "$PWD" /path/corrected/chronicle_bundle.json /tmp/corrected-records.json
NODE_PATH=/path/to/playwright/node_modules PYTHONPATH=src node docs/superpowers/progress/connected-world-rework-viewer-compatibility/journey-corrected.mjs "$PWD/viewer/dist" /path/corrected/chronicle_bundle.json /tmp/corrected-browser /path/to/python
```

The archive profiler config embeds input hashes, source build path, timing budget and sample plan; change only paths when replaying the same measurements. Recreate the residual runtime with the earlier `profile-index.mjs` at `cf0925d9`, then run `profile-index-residual.mjs RUNTIME BUNDLE OUTPUT`. Absolute machine paths in receipts identify the actual environment; they are not a promise that a reclaimed container restarts. Initial diagnostic-tool setup errors are retained in [tool failures](tool-failures.json); neither spent seeds nor invalidated a measured sample.

The [120-turn complete-window follow-up](complete-window-120.md) adds 372 real browser assertions and all-snapshot prior-frame readback without changing the frozen viewer. The original 50-check layout receipts use the script pinned at `2b27dcf5`; the later journey adds snapshot selection, public-health row checks and explicit history pagination.

Independent review corrected the follow-up's comparison-only count from an invalid 2,392 to **2,163** after fixing complete sparse empty-region zeros. The [correction record](complete120-counter-correction.json) preserves the old receipt and new independent next-PH regression. All 3,840 prior-frame assertions and 372 browser assertions remain valid.
