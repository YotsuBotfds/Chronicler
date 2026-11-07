# Connected history viewer: measured formatting cost and unchanged evidence

This is the **pure formatter optimization** from source
`2726bf449d0e4d581a72034000ee0861a58ee439` to
`cf0925d93fe1dff4687326e2d583d3d727d6c0a4`. Later correctness/schema and gzip
work is separate and is not included in these measurements. No simulation,
native code, data, history horizon, feature or sample bound changed.

The accepted natural FULL procedural-19, 120-turn bundle has SHA256
`f6cb5562a4aaec888b6f2a03b4c4b01bd1e8d49737aec22673034eba30ce0ee2`.
The unchanged production journey reproduces the earlier history-panel problem:
initial opening **4,653 ms desktop / 4,400 ms phone**. After the optimization,
the same journey is **1,334 / 1,425 ms**, with all **30 checks passing on each
build**. [Before](before-browser.json), [after](after-browser.json), and
[visually inspected phone capture](after-phone.png) retain source pointers,
actual wages/withholding, chain/person/project/region/search navigation and
overflow/console checks. Wide tables scroll independently.

## Cause and semantic checks

The production index builds 190,555 observations and 3,279 named entities.
A diagnostic wrapper around `Number.prototype.toLocaleString` measured
**203,160 calls, 3,669 ms of a 4,352 ms index build** (about 84%). Repeating with
complete semantic hashing measured 4,870 ms before and 612 ms after. Each old
call constructed the same locale/precision machinery. Reusing one
`Intl.NumberFormat(undefined, {maximumFractionDigits: 3})` per document removes
that repeated work. Every row, string, state, order, pointer and identity stays.

The complete index digest is identical:
`ff4554e9f262cc6804e1c8a04c478ede21c3bb5aa19fb95b120d363e83b21e0d`.
Twenty-eight person/household/region/project/order/army and through-turn query
results also have an identical digest. [Locale receipts](locales/) independently
repeat complete-index and query equality under **en-US, de-DE, fr-FR and ar-EG**.
Large numbers, rounding, negative zero, infinities and NaN format identically
to the former operation. Nonfinite saved income still becomes **malformed**
through the public strict reader; it is not rendered as a valid number. The
focused six-file suite passes **34 tests**, including that regression. Build
passes with the pre-existing large-chunk advisory. These are not substitutes
for the integration owner's full viewer and exact-head CI gates.

## Fixed pilot, budget and repeated measurements

The [pilot](pilot.json) used the exact two immutable production builds, the same
120-turn input and one fresh desktop/phone context per variant: 40.996 seconds.
Three repeats across four fixed input sizes project roughly 558 seconds;
the 1.5 margin gives 837 seconds, below the declared **900-second elapsed
ceiling**. Actual complete run: **541.995 seconds, 48/48 measurements**, no
browser errors. This is an elapsed budget, not a claimed single-core CPU cost.

The same browser process runs new isolated contexts in alternating build order
for each case/repeat. A cold sample includes actual file upload, decode worker,
map readiness, first panel import and complete index/render work. Warm means
switching to Epidemics and reopening Livelihoods on the same page; it does not
hide a prebuilt history index. End-of-run scrubbing and selecting the same
recorded entity are timed separately. Browser phone/touch is Chromium at
390×844 on this host, **without handset CPU emulation**; desktop is 1440×900.
OS file caches may be warm. All samples, including adverse values, are retained.

Medians of three samples, before → after, in milliseconds:

| Unchanged input | Viewport | File load | Cold panel | Warm reopen | Latest turn |
| --- | --- | ---: | ---: | ---: | ---: |
| procedural 19, 120 turns | desktop | 2,204 → 1,887 | 4,609 → 1,151 | 4,393 → 947 | 671 → 665 |
| procedural 19, 120 turns | phone | 1,921 → 1,796 | 4,456 → 1,157 | 4,494 → 1,038 | 861 → 907 |
| procedural 19, 200 turns | desktop | 3,175 → 3,691 | 8,350 → 1,978 | 8,484 → 1,596 | 1,098 → 1,027 |
| procedural 19, 200 turns | phone | 3,091 → 3,421 | 8,792 → 1,938 | 8,338 → 1,465 | 1,118 → 964 |
| procedural 48, 150 turns | desktop | 2,670 → 2,738 | 6,495 → 1,595 | 6,236 → 1,367 | 902 → 898 |
| procedural 48, 150 turns | phone | 2,570 → 2,984 | 6,507 → 1,668 | 6,253 → 1,428 | 1,012 → 1,030 |
| 53,138 peak native agents, 20 turns | desktop | 940 → 909 | 1,495 → 1,102 | 1,467 → 1,047 | 1,098 → 932 |
| 53,138 peak native agents, 20 turns | phone | 797 → 743 | 1,376 → 928 | 1,394 → 999 | 989 → 930 |

The stress configuration initializes 43,700 agents and reaches 53,138; its short
history has fewer recorded observations than the 120/200-turn worlds. It is
not evidence about a long 53,138-agent history. Input hashes, all initial/latest
turns, region/snapshot counts, available entities, selected IDs and displayed
row counts match within **every before/after pair**. No evidence was dropped.

The post-pilot host targets (median cold panel ≤2.5 seconds at 120 turns and
≤4 seconds at 200 turns) are met. Cold history opening improves about **74–78%**
on the long-history cases and **26–33%** on the short stress case. This is a
bounded shared-host observation with only three repetitions, not qualification
or a hardware-independent latency guarantee.

**Remaining costs and adverse measurements:** no file-load speedup is claimed.
The 200-turn file loads and the 48-region phone load were slower in these
samples. Late-turn navigation remains roughly 0.7–1.2 seconds, and the short
stress desktop's entity selection was slower (median **167 → 276 ms**). Sampled
renderer JS heap is mixed: 120-turn cold heap rose about **120.6 → 134.9 MiB**
desktop and **120.5 → 133.0 MiB** phone; other cases differ. GC timing and shared
host noise are not isolated. These are JS-heap snapshots, **not browser RSS**.
No memory, wire-size or simulation-throughput improvement is claimed here.
All medians/ranges/paired differences, renderer CPU phases and heap samples are
in [paired-summary.json](paired-summary.json), with every raw measurement and
asset hash in [paired.json](paired.json).

## Reproduction and retained identities

[source.json](source.json) binds the commits and production source bytes;
[environment.json](environment.json) records Node/Chromium and the four-CPU,
16-GiB cgroup. The original build-race orchestration failure is retained in
[initial-setup-failure.json](initial-setup-failure.json); it never produced a
performance sample. No held seed, simulation, paid narration, default or
credential changed. Raw inputs/builds remain in the execution workspace; their
lifetime after reclamation is not promised.

Create separate worktrees at the two commits, install the existing locked
viewer dependencies, and build each to a separate immutable directory. Adjust
the retained `config.builds` and `config.cases[*].bundle` paths to those files;
keep their hashes, world sizes and horizons. Run the same tool:

```sh
NODE_PATH=BROWSER_NODE_MODULES CHROMIUM_EXECUTABLE=/usr/bin/chromium PYTHONPATH=src \
  node docs/superpowers/progress/connected-world-rework-viewer/profile-browser.mjs \
  --config CONFIG.json --out EVIDENCE --python NATIVE/bin/python
```

Use [profile-index.mjs](profile-index.mjs) for the full production-code index,
query and locale diagnostic:

```sh
LANG=de_DE.UTF-8 LC_ALL=de_DE.UTF-8 NODE_PATH=CHECKOUT/viewer/node_modules \
  node docs/superpowers/progress/connected-world-rework-viewer/profile-index.mjs \
  --source-root CHECKOUT --bundle RAW/chronicle_bundle.json --out index.json
```

Repeat both source commits under each recorded locale and compare
`index_sha256`, `queries_sha256`, dimensions and primitive results. A fresh
development bundle can be regenerated from its frozen source/command in the
existing CW6/profile evidence; consumed held cohorts must not be reused.
